"""Everything that touches the GPU: the warm sd-server engine, the cold sd-cli path,
the ESRGAN upscaler, and the Qwen3-VL assistant (llama.cpp).

Only one of these runs at a time. The job queue in server.py makes sure of that.
"""
import base64
import json
import math
import os
import re
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
BIN = os.path.join(ROOT, "bin")
MODELS = os.path.join(ROOT, "models")

SD_CLI = os.path.join(BIN, "sd-cli")
SD_SERVER = os.path.join(BIN, "sd-server")
DIFFUSION = os.path.join(MODELS, "qwen-image-2.1-Q4_K_M.gguf")
LLM = os.path.join(MODELS, "Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf")
VISION = os.path.join(MODELS, "mmproj-Qwen3VL-8B-Instruct-F16.gguf")
VAE = os.path.join(MODELS, "qwen_image_2.1_vae_bf16.safetensors")
LORAS = os.path.join(MODELS, "loras")
UPSCALER = os.path.join(MODELS, "upscalers", "RealESRGAN_x4plus.pth")

TURBO_LORA = "fun-acc-4step"
# Grid the Fun-Acc LoRA was distilled on (2048 px). "matched" shifts it to the output size.
TRAINED_SIGMAS = [1.0, 0.9169867038726807, 0.7861579060554504, 0.5494909882545471, 0.0]

# Untiled VAE encode/decode is about 2x faster and fits in 16 GB up to roughly this size.
TILE_ABOVE_MP = 1.25

STEP_RE = re.compile(r"(\d+)/(\d+) - ([\d.]+)(s/it|it/s)")


def turbo_available():
    return os.path.exists(os.path.join(LORAS, TURBO_LORA + ".safetensors"))


def upscaler_available():
    return os.path.exists(UPSCALER)


def llama_cli():
    """llama-mtmd-cli from the llama.cpp build in bin/llama/, if present."""
    base = os.path.join(BIN, "llama")
    if os.path.isdir(base):
        for d in sorted(os.listdir(base), reverse=True):
            p = os.path.join(base, d, "llama-mtmd-cli")
            if os.path.exists(p):
                return p
    return None


def turbo_sigmas(width, height, schedule="matched"):
    """4-step sigmas for the Turbo LoRA.

    The LoRA was distilled on a fixed grid for 2048 px (mu about 1.474 on Qwen's 32-step
    exponential schedule, sampled every 8 steps). For other sizes we move mu by the same amount
    Qwen's own dynamic shift would, which keeps the shape of the grid but matches the token count.
    At 768 px this produced visibly sharper edits and followed secondary instructions better.
    """
    if schedule != "matched":
        return list(TRAINED_SIGMAS)

    def native_mu(tokens):
        m = (0.9 - 0.5) / (8192 - 256)
        return 0.5 + m * (tokens - 256)

    mu = 1.474 - (native_mu((2048 // 16) ** 2) - native_mu((width // 16) * (height // 16)))
    n = 32
    ts = [1 - i * (1 - 1 / n) / (n - 1) for i in range(n)]
    s = [math.exp(mu) / (math.exp(mu) + (1 / t - 1)) for t in ts]
    one_minus = [1 - x for x in s]
    scale = one_minus[-1] / (1 - 0.02)  # shift_terminal from Qwen's scheduler config
    grid = [1 - (z / scale) for z in one_minus] + [0.0]
    return [round(x, 6) for x in grid[::8]]


def needs_tiling(width, height):
    return width * height / 1048576.0 > TILE_ABOVE_MP


# ---------------------------------------------------------------- progress parsing

class Progress:
    """Turns sd-cli / sd-server log lines into job fields (stage, step, speed, eta)."""

    def __init__(self, job):
        self.job = job
        self.sampling = False  # VAE tiling also prints N/M bars; only count denoiser steps

    def feed(self, line):
        job = self.job
        if "generating image:" in line:
            self.sampling = True
            job["stage"] = "Loading diffusion model"
            return
        m = STEP_RE.search(line) if self.sampling else None
        if m:
            step, total, val, unit = int(m.group(1)), int(m.group(2)), float(m.group(3)), m.group(4)
            spi = val if unit == "s/it" else (1.0 / val if val else 0)
            job.update(step=step, total=total, sec_per_it=round(spi, 1), stage="Sampling")
            job["eta"] = round(spi * (total - step) + 20)
        elif "get_learned_condition completed" in line:
            job["stage"] = "Prompt encoded"
        elif "latent images completed" in line:
            self.sampling = False
            job["stage"] = "Decoding image"
            job["eta"] = 25
        elif "[ERROR" in line:
            job["error"] = line.split("]", 1)[-1].strip()[:300]


def pump(stream, on_line, log=None):
    """Read a subprocess stream, splitting on \\r and \\n so progress bars arrive live."""
    buf = b""
    while True:
        chunk = os.read(stream.fileno(), 4096)
        if not chunk:
            break
        if log:
            log.write(chunk)
        buf += chunk
        parts = re.split(rb"[\r\n]", buf)
        buf = parts.pop()
        for raw in parts:
            on_line(raw.decode("utf-8", "replace"))


# ---------------------------------------------------------------- warm engine (sd-server)

class Cancelled(Exception):
    pass


class WarmEngine:
    """A long-lived sd-server process.

    Weights are memory-mapped from disk (--params-backend disk), so the idle process holds
    about 1 GB and macOS can reclaim the rest under pressure instead of swapping. What stays
    warm is the process, its compute graphs and the prompt conditioning cache.
    """

    def __init__(self):
        self.proc = None
        self.port = None
        self.lock = threading.Lock()
        self.listener = None      # callable(line) for the job currently running
        self.log = None           # open file for the current job's log, or None
        self.last_used = 0.0
        self.idle_seconds = 600
        threading.Thread(target=self._idle_watch, daemon=True).start()

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def _free_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def start(self):
        with self.lock:
            if self.running:
                return
            self.port = self._free_port()
            cmd = [SD_SERVER, "--listen-port", str(self.port),
                   "--diffusion-model", DIFFUSION, "--llm", LLM, "--llm_vision", VISION, "--vae", VAE,
                   "--lora-model-dir", LORAS, "--diffusion-fa",
                   "--model-args", "qwen_image_2_1_prefix_cache_type=q8_0",
                   "--mmap", "--params-backend", "disk", "--disable-image-metadata",
                   # remember more recent prompts so re-runs and variations skip the 5-10 s encoding
                   "--conditioning-cache-size", "12"]
            self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         start_new_session=True)
            threading.Thread(target=pump, args=(self.proc.stdout, self._on_line), daemon=True).start()
        deadline = time.time() + 120
        while time.time() < deadline:
            if not self.running:
                raise RuntimeError("The engine exited while starting")
            try:
                self._get("/sdcpp/v1/capabilities", timeout=2)
                self.last_used = time.time()
                return
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        self.stop()
        raise RuntimeError("The engine did not start in time")

    def stop(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                    self.proc.wait(timeout=10)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(self.proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            self.proc = None

    def _on_line(self, line):
        if self.log:
            try:
                self.log.write((line + "\n").encode())
            except ValueError:
                pass
        if self.listener:
            self.listener(line)

    def _idle_watch(self):
        while True:
            time.sleep(15)
            if self.running and self.listener is None and time.time() - self.last_used > self.idle_seconds:
                self.stop()

    def _get(self, path, timeout=10):
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=timeout) as r:
            return json.load(r)

    def _post(self, path, body):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    def generate(self, body, job, log=None):
        """Run one img_gen request. Returns PNG bytes. Raises Cancelled if the job is cancelled."""
        self.start()
        progress = Progress(job)
        self.listener, self.log = progress.feed, log
        try:
            sub = self._post("/sdcpp/v1/img_gen", body)
            while True:
                if job.get("state") == "cancelled":
                    # sd-server can't stop a running job, so restart the engine instead
                    self.stop()
                    raise Cancelled()
                try:
                    st = self._get(sub["poll_url"])
                except (urllib.error.URLError, OSError):
                    if job.get("state") == "cancelled":
                        raise Cancelled()
                    raise RuntimeError("The engine stopped unexpectedly")
                if st["status"] == "completed":
                    return base64.b64decode(st["result"]["images"][0]["b64_json"])
                if st["status"] in ("failed", "cancelled"):
                    err = (st.get("error") or {}).get("message") or st["status"]
                    raise RuntimeError(job.get("error") or err)
                time.sleep(0.5)
        finally:
            self.listener, self.log = None, None
            self.last_used = time.time()


ENGINE = WarmEngine()


# ---------------------------------------------------------------- cold processes (sd-cli, llama.cpp)

class ColdRun:
    """Runs one subprocess, streaming its output into a Progress parser."""

    current = None  # the ColdRun in flight, so cancel() can reach it

    def __init__(self, cmd, job, log=None):
        self.cmd, self.job, self.log = cmd, job, log
        self.proc = None

    def run(self, collect=False):
        ColdRun.current = self
        progress = Progress(self.job)
        out = []

        def on_line(line):
            progress.feed(line)
            if collect:
                out.append(line)
        try:
            self.proc = subprocess.Popen(self.cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL if collect else subprocess.STDOUT,
                                         start_new_session=True)
            pump(self.proc.stdout, on_line, self.log)
            rc = self.proc.wait()
        finally:
            ColdRun.current = None
        if self.job.get("state") == "cancelled":
            raise Cancelled()
        return rc, out

    @staticmethod
    def cancel():
        run = ColdRun.current
        if run and run.proc:
            try:
                os.killpg(run.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def assistant(image_path, task, job):
    """Ask Qwen3-VL about an image. task is "describe" or "suggest". Returns text."""
    cli = llama_cli()
    if not cli:
        raise RuntimeError("llama.cpp is not installed. Run ./download.sh")
    prompts = {
        "describe": "Describe this image as one detailed prompt for an image generator. "
                    "Cover subject, setting, lighting, colors, camera and style. One paragraph, no preamble.",
        "suggest": "Suggest 6 creative but realistic edits for this image. Each on its own line, "
                   "as a short instruction under 12 words. No numbering, no extra text.",
    }
    cmd = [cli, "-m", LLM, "--mmproj", VISION, "--image", image_path, "-ngl", "99",
           "--temp", "0.5", "-n", "300", "-c", "4096", "--no-warmup", "-p", prompts[task]]
    job["stage"] = "Looking at the image"
    rc, out = ColdRun(cmd, job).run(collect=True)
    if rc != 0:
        raise RuntimeError("The assistant failed (exit code %s)" % rc)
    text = "\n".join(out).strip()
    if task == "suggest":
        lines = [re.sub(r"^[\s\-\*\d\.\)]+", "", l).strip() for l in text.splitlines()]
        return [l for l in lines if 3 < len(l) < 120][:8]
    return text
