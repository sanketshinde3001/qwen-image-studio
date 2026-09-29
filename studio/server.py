#!/usr/bin/env python3
"""Qwen-Image Studio: a small local web UI for Qwen-Image 2.1 on stable-diffusion.cpp.

Standard library only. Everything it writes stays inside the project folder:
  outputs/         generated, edited and upscaled images, each with a .json settings sidecar
  inputs/          uploaded images and masks (converted to PNG)
  logs/            one log per job
  studio/tmp/      resized references, previews, and private-mode files (wiped on start and exit)
  studio/*.json    calibration, settings, saved presets and favorites
"""
import base64
import io
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import engine
from engine import ENGINE, Cancelled, ColdRun

STUDIO = engine.STUDIO
ROOT = engine.ROOT
OUTPUTS = os.path.join(ROOT, "outputs")
INPUTS = os.path.join(ROOT, "inputs")
LOGS = os.path.join(ROOT, "logs")
TMP = os.path.join(STUDIO, "tmp")
PRIVATE = os.path.join(TMP, "private")
CALIB = os.path.join(STUDIO, "calibration.json")
SETTINGS = os.path.join(STUDIO, "settings.json")
LIBRARY = os.path.join(STUDIO, "library.json")
for d in (OUTPUTS, INPUTS, TMP, LOGS):
    os.makedirs(d, exist_ok=True)

SAMPLERS = ["euler", "euler_a", "heun", "dpm++2m", "dpm++2m_sde", "res_multistep", "ipndm", "lcm", "ddim_trailing"]
SCHEDULERS = ["default", "simple", "discrete", "karras", "exponential", "sgm_uniform", "beta", "smoothstep", "kl_optimal"]
GEN_MODES = ("gen", "edit")


# ---------------------------------------------------------------- small helpers

def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def wipe_private():
    shutil.rmtree(PRIVATE, ignore_errors=True)
    os.makedirs(PRIVATE)


def wipe_tmp():
    """Resized refs and previews from interrupted jobs, plus any private files left by a crash."""
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(PRIVATE)


def image_size(path):
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
                         capture_output=True, text=True).stdout
    return int(re.search(r"pixelWidth: (\d+)", out).group(1)), int(re.search(r"pixelHeight: (\d+)", out).group(1))


def to_png(src, dst, max_side=None, exact=None):
    """Convert to PNG. max_side shrinks (never enlarges); exact=(w, h) resizes to that size."""
    args = ["sips", "-s", "format", "png"]
    if exact:
        args += ["-z", str(exact[1]), str(exact[0])]
    elif max_side:
        w, h = image_size(src)
        if max(w, h) > max_side:
            args += ["-Z", str(max_side)]
    r = subprocess.run(args + [src, "--out", dst], capture_output=True)
    return r.returncode == 0 and os.path.exists(dst)


def data_url(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def snap16(v):
    return max(256, int(round(v / 16.0)) * 16)


def safe_name(name):
    base = os.path.basename(name or "")
    if not base or base != name or base.startswith("."):
        raise ValueError("bad name")
    return base


def ref_path(name):
    """A reference can be an upload (inputs/), a private file, or an earlier result (outputs/)."""
    for d in (INPUTS, PRIVATE):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return os.path.join(OUTPUTS, name)


def is_private_file(name):
    return bool(name) and os.path.exists(os.path.join(PRIVATE, name))


def write_sidecar(image_path, meta):
    write_json(image_path.rsplit(".", 1)[0] + ".json", meta)


def sidecar_of(name):
    return read_json(os.path.join(OUTPUTS, name.rsplit(".", 1)[0] + ".json"), {})


# ---------------------------------------------------------------- estimates

DEFAULT_CALIB = {
    # wall-clock seconds per step per MP^1.2 on an M5 / 16 GB (see README benchmarks)
    "gen": 79.0, "edit": 87.0, "gen_fast": 24.0, "edit_fast": 25.0, "gen_turbo": 50.0, "edit_turbo": 26.0,
    "upscale": 355.0,  # seconds per input MP for ESRGAN x4
}


def load_calib():
    c = dict(DEFAULT_CALIB)
    c.update(read_json(CALIB, {}))
    return c


def work_mp(job):
    """Megapixels the transformer attends over: output plus reference images."""
    mp = job["width"] * job["height"] / 1048576.0
    for r in job.get("ref_sizes", []):
        mp += r[0] * r[1] / 1048576.0
    return mp


def calib_key(job):
    speed = "_turbo" if job.get("turbo") else "_fast" if job.get("fast") else ""
    return job["mode"] + speed


def estimate_seconds(job):
    c = load_calib()
    if job["mode"] == "upscale":
        return c["upscale"] * job["src_mp"] + 5
    if job["mode"] == "assist":
        return 25
    return c.get(calib_key(job), 80.0) * (work_mp(job) ** 1.2) * job["steps"] + 30


def learn_speed(job):
    if job.get("private"):
        return  # private mode writes nothing, not even speed data
    c = read_json(CALIB, {})
    spent = job["finished"] - job["started"]
    if job["mode"] == "upscale":
        c["upscale"] = round(spent / max(0.05, job["src_mp"]), 1)
    elif job["mode"] in GEN_MODES:
        c[calib_key(job)] = round(max(1.0, spent - 30) / (job["steps"] * work_mp(job) ** 1.2), 2)
    write_json(CALIB, c)


# ---------------------------------------------------------------- settings and library

SETTINGS_DEFAULT = {"idle_minutes": 10}


def load_settings():
    s = dict(SETTINGS_DEFAULT)
    s.update(read_json(SETTINGS, {}))
    return s


def apply_settings(s):
    ENGINE.idle_seconds = max(1, int(s.get("idle_minutes", 10))) * 60


def load_library():
    lib = read_json(LIBRARY, {})
    return {"presets": lib.get("presets", {}), "favorites": lib.get("favorites", [])}


# ---------------------------------------------------------------- job queue

JOBS = {}      # id -> job dict
ORDER = []     # ids in submission order (queued ones can be reordered)
LOCK = threading.Lock()
WAKE = threading.Event()
QUEUE = {"paused": False}
# Private mode lives on the server so a page reload or a second tab can't silently turn it off.
PRIVATE_MODE = {"on": False}

PUBLIC_KEYS = ("id", "mode", "state", "prompt", "width", "height", "steps", "seed", "step", "total",
               "sec_per_it", "stage", "created", "started", "finished", "eta", "estimate", "output",
               "error", "refs", "has_preview", "private", "turbo", "task", "source", "result", "engine")


def public(job):
    return {k: job.get(k) for k in PUBLIC_KEYS}


def drop_jobs(pred):
    with LOCK:
        for i in list(ORDER):
            if pred(JOBS[i]):
                ORDER.remove(i)
                JOBS.pop(i)


def prepare_refs(job):
    """Resize references to the chosen detail level, and build init + mask for masked edits."""
    job["ref_paths"], job["ref_sizes"] = [], []
    for i, ref in enumerate(job.get("refs", [])):
        dst = os.path.join(TMP, "%s_ref%d.png" % (job["id"], i))
        to_png(ref_path(ref), dst, max_side=job.get("ref_max", 768))
        job["ref_paths"].append(dst)
        job["ref_sizes"].append(image_size(dst))
    job["init_path"] = job["mask_path"] = None
    if job.get("mask") and job["refs"]:
        size = (job["width"], job["height"])
        job["init_path"] = os.path.join(TMP, job["id"] + "_init.png")
        job["mask_path"] = os.path.join(TMP, job["id"] + "_mask.png")
        to_png(ref_path(job["refs"][0]), job["init_path"], exact=size)
        to_png(ref_path(job["mask"]), job["mask_path"], exact=size)


def engine_body(job):
    body = {
        "prompt": job["prompt"], "width": job["width"], "height": job["height"], "seed": job["seed"],
        "batch_count": 1, "output_format": "png", "embed_image_metadata": False,
        "ref_images": [data_url(p) for p in job["ref_paths"]],
        "vae_tiling_params": {"enabled": engine.needs_tiling(job["width"], job["height"])},
        "sample_params": {"sample_method": job["sampler"], "sample_steps": job["steps"],
                          "guidance": {"txt_cfg": job["cfg"]}},
    }
    sp = body["sample_params"]
    if job["turbo"]:
        sp["custom_sigmas"] = engine.turbo_sigmas(job["width"], job["height"], job.get("turbo_schedule"))
        body["lora"] = [{"path": engine.TURBO_LORA + ".safetensors", "multiplier": 1.0}]
    else:
        body["negative_prompt"] = job.get("negative") or ""
        if job.get("img_cfg"):
            sp["guidance"]["img_cfg"] = job["img_cfg"]
        if job.get("scheduler") not in (None, "default"):
            sp["scheduler"] = job["scheduler"]
        if job.get("flow_shift"):
            sp["flow_shift"] = job["flow_shift"]
        if job.get("fast"):
            body["cache_mode"], body["cache_option"] = "easycache", "threshold=%s" % job["fast_threshold"]
    if job["init_path"]:
        body.update(init_image=data_url(job["init_path"]), mask_image=data_url(job["mask_path"]), strength=1.0)
    return body


def cli_cmd(job, out_path, preview_path):
    prompt = ("<lora:%s:1>" % engine.TURBO_LORA if job["turbo"] else "") + job["prompt"]
    cmd = [engine.SD_CLI, "--diffusion-model", engine.DIFFUSION, "--llm", engine.LLM, "--vae", engine.VAE,
           "-p", prompt, "--steps", str(job["steps"]), "--cfg-scale", str(job["cfg"]),
           "--sampling-method", job["sampler"], "-W", str(job["width"]), "-H", str(job["height"]),
           "--seed", str(job["seed"]), "--diffusion-fa", "--disable-image-metadata",
           "--model-args", "qwen_image_2_1_prefix_cache_type=q8_0", "-o", out_path]
    if engine.needs_tiling(job["width"], job["height"]):
        cmd.append("--vae-tiling")
    if job["turbo"]:
        sig = engine.turbo_sigmas(job["width"], job["height"], job.get("turbo_schedule"))
        cmd += ["--lora-model-dir", engine.LORAS, "--sigmas", ",".join(str(s) for s in sig)]
    else:
        if job.get("negative"):
            cmd += ["-n", job["negative"]]
        if job.get("scheduler") not in (None, "default"):
            cmd += ["--scheduler", job["scheduler"]]
        if job.get("flow_shift"):
            cmd += ["--flow-shift", str(job["flow_shift"])]
        if job.get("fast"):
            cmd += ["--cache-mode", "easycache", "--cache-option", "threshold=%s" % job["fast_threshold"]]
        if job.get("img_cfg") and job["mode"] == "edit":
            cmd += ["--img-cfg-scale", str(job["img_cfg"])]
    if job.get("preview"):
        cmd += ["--preview", "proj", "--preview-path", preview_path, "--preview-interval", "1"]
    if job["mode"] == "edit":
        cmd += ["--llm_vision", engine.VISION]
        for r in job["ref_paths"]:
            cmd += ["-r", r]
    if job["init_path"]:
        cmd += ["-i", job["init_path"], "--mask", job["mask_path"], "--strength", "1.0"]
    return cmd


def open_log(job, name):
    """Per-job log. Private jobs get none. The output name is written first so delete can find it."""
    if job.get("private"):
        return None
    log = open(os.path.join(LOGS, "studio-%s-%s.log" % (time.strftime("%Y%m%d-%H%M%S"), job["id"])), "wb")
    log.write(("output: %s\nmode: %s  size: %dx%d  seed: %s  engine: %s\n\n" % (
        name, job["mode"], job["width"], job["height"], job.get("seed"), job.get("engine"))).encode())
    return log


def run_image_job(job):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    private = job["private"]
    name = "%s_%s_%dx%d_s%d.png" % (stamp, job["mode"], job["width"], job["height"], job["seed"])
    out_path = os.path.join(PRIVATE if private else OUTPUTS, name)
    preview_path = os.path.join(TMP, job["id"] + "_preview.png")
    prepare_refs(job)
    job["estimate"] = round(estimate_seconds(job))
    # Live preview needs sd-cli. Everything else runs on the warm engine.
    job["engine"] = "cold" if job.get("preview") else "warm"
    job.update(state="running", started=time.time(), step=0,
               stage="Starting engine" if job["engine"] == "warm" and not ENGINE.running else "Encoding prompt")
    log = open_log(job, name)
    try:
        if job["engine"] == "warm":
            png = ENGINE.generate(engine_body(job), job, log)
            with open(out_path, "wb") as f:
                f.write(png)
        else:
            ENGINE.stop()  # never hold two copies of the models in 16 GB
            watcher = threading.Thread(target=watch_preview, args=(job, preview_path), daemon=True)
            watcher.start()
            rc, _ = ColdRun(cli_cmd(job, out_path, preview_path), job, log).run()
            if rc != 0 or not os.path.exists(out_path):
                raise RuntimeError(job.get("error") or "sd-cli exited with code %s" % rc)
    finally:
        if log:
            log.close()
        job["has_preview"] = False
        for p in [preview_path, job.get("init_path"), job.get("mask_path")] + job["ref_paths"]:
            if p and os.path.exists(p):
                os.remove(p)
    finish(job, name, {k: job.get(k) for k in (
        "mode", "prompt", "negative", "width", "height", "steps", "cfg", "img_cfg", "seed", "sampler",
        "scheduler", "flow_shift", "fast", "fast_threshold", "refs", "ref_max", "turbo", "turbo_schedule", "mask")})


def watch_preview(job, path):
    while job["state"] == "running":
        job["has_preview"] = os.path.exists(path)
        time.sleep(0.5)


def run_upscale_job(job):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    src = ref_path(job["source"])
    sw, sh = image_size(src)
    job["width"], job["height"] = sw * job["scale"], sh * job["scale"]
    name = "%s_upscale_%dx%d.png" % (stamp, job["width"], job["height"])
    out_path = os.path.join(PRIVATE if job["private"] else OUTPUTS, name)
    tmp_out = os.path.join(TMP, job["id"] + "_x4.png")
    job.update(state="running", started=time.time(), stage="Upscaling", engine="cold")
    log = open_log(job, name)
    try:
        cmd = [engine.SD_CLI, "-M", "upscale", "--upscale-model", engine.UPSCALER, "-i", src,
               "--disable-image-metadata", "-o", tmp_out]
        rc, _ = ColdRun(cmd, job, log).run()
        if rc != 0 or not os.path.exists(tmp_out):
            raise RuntimeError("The upscaler failed (exit code %s)" % rc)
        # ESRGAN is x4; for x2 shrink the result, which keeps the extra detail
        to_png(tmp_out, out_path, exact=(job["width"], job["height"]) if job["scale"] != 4 else None)
    finally:
        if log:
            log.close()
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
    base = read_json(os.path.join(OUTPUTS, job["source"].rsplit(".", 1)[0] + ".json"), {}) or job.get("source_meta") or {}
    meta = dict(base, mode="upscale", base_mode=base.get("mode"), refs=[job["source"]], scale=job["scale"],
                width=job["width"], height=job["height"])
    finish(job, name, meta)


def run_assist_job(job):
    job.update(state="running", started=time.time(), stage="Loading Qwen3-VL", engine="cold")
    job["result"] = engine.assistant(ref_path(job["source"]), job["task"], job)
    job.update(state="done", stage="Done", finished=time.time(), eta=0)


def finish(job, name, meta):
    job["finished"] = time.time()
    meta.update(seconds=round(job["finished"] - job["started"]), sec_per_it=job.get("sec_per_it"),
                created=time.strftime("%Y%m%d-%H%M%S"))
    job.update(state="done", output=name, stage="Done", eta=0)
    learn_speed(job)
    if job["private"]:
        job["meta"] = meta  # memory only; written if the user presses Keep
    else:
        write_sidecar(os.path.join(OUTPUTS, name), meta)


def worker():
    while True:
        WAKE.wait()
        with LOCK:
            nxt = None if QUEUE["paused"] else next((JOBS[i] for i in ORDER if JOBS[i]["state"] == "queued"), None)
            if nxt is None:
                WAKE.clear()
                continue
            nxt["state"] = "starting"
        try:
            {"upscale": run_upscale_job, "assist": run_assist_job}.get(nxt["mode"], run_image_job)(nxt)
        except Cancelled:
            nxt.update(state="cancelled", stage="Cancelled")
        except Exception as e:  # keep the worker alive
            if nxt["state"] != "cancelled":
                nxt.update(state="error", error=str(e)[:300], stage="Failed")


def new_job(mode, private, **fields):
    job = {"id": uuid.uuid4().hex[:10], "mode": mode, "state": "queued", "private": private,
           "created": time.time(), "step": 0, "total": None, "prompt": "", "width": 0, "height": 0,
           "steps": 0, "seed": None, "refs": [], "ref_sizes": [], "turbo": False}
    job.update(fields)
    job["estimate"] = round(estimate_seconds(job))
    return job


def enqueue(jobs):
    with LOCK:
        for job in jobs:
            JOBS[job["id"]] = job
            ORDER.append(job["id"])
    WAKE.set()
    return [j["id"] for j in jobs]


def submit(spec):
    mode = spec.get("mode", "gen")
    if mode in ("upscale", "assist"):
        return submit_tool(mode, spec)
    if mode not in GEN_MODES:
        raise ValueError("Unknown mode")
    prompt = (spec.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Prompt is required")
    refs = [safe_name(r) for r in spec.get("refs", [])][:3]
    if mode == "edit" and not refs:
        raise ValueError("Add at least one image to edit")
    mask = safe_name(spec["mask"]) if spec.get("mask") and mode == "edit" else None
    seed = int(spec.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**31 - 1)
    turbo = bool(spec.get("turbo")) and engine.turbo_available()
    # anything made from a private image stays private
    private = PRIVATE_MODE["on"] or bool(spec.get("private")) or any(is_private_file(r) for r in refs + [mask])
    jobs = []
    for i in range(max(1, min(8, int(spec.get("batch", 1))))):
        job = dict(
            prompt=prompt, negative=(spec.get("negative") or "").strip(),
            width=snap16(int(spec.get("width", 768))), height=snap16(int(spec.get("height", 768))),
            steps=max(1, min(100, int(spec.get("steps", 16)))), cfg=float(spec.get("cfg", 6.0)),
            img_cfg=spec.get("img_cfg") and float(spec["img_cfg"]), seed=seed + i,
            sampler=spec.get("sampler") if spec.get("sampler") in SAMPLERS else "euler",
            scheduler=spec.get("scheduler") if spec.get("scheduler") in SCHEDULERS else "default",
            flow_shift=spec.get("flow_shift") and float(spec["flow_shift"]),
            fast=bool(spec.get("fast")), fast_threshold=float(spec.get("fast_threshold", 0.2)),
            preview=bool(spec.get("preview")), refs=refs, mask=mask,
            ref_max=int(spec.get("ref_max", 768)), turbo=turbo,
            turbo_schedule="trained" if spec.get("turbo_schedule") == "trained" else "matched")
        if turbo:
            job.update(steps=4, cfg=1.0, img_cfg=None, negative="", sampler="euler", scheduler="default",
                       flow_shift=None, fast=False)
        sizes = []
        for r in refs:
            w, h = image_size(ref_path(r))
            s = min(1.0, job["ref_max"] / float(max(w, h)))
            sizes.append((w * s, h * s))
        jobs.append(new_job(mode, private, ref_sizes=sizes, **job))
    return enqueue(jobs)


def submit_tool(mode, spec):
    source = safe_name(spec.get("source"))
    path = ref_path(source)
    if not os.path.exists(path):
        raise ValueError("Image not found")
    private = PRIVATE_MODE["on"] or is_private_file(source)
    w, h = image_size(path)
    if mode == "upscale":
        if not engine.upscaler_available():
            raise ValueError("The upscaler model is missing. Run ./download.sh")
        scale = 2 if int(spec.get("scale", 4)) == 2 else 4
        meta = next((j.get("meta") for j in JOBS.values() if j.get("output") == source), None)
        job = new_job("upscale", private, source=source, scale=scale, refs=[source], src_mp=w * h / 1048576.0,
                      prompt=(sidecar_of(source) or meta or {}).get("prompt") or "Upscale",
                      width=w * scale, height=h * scale, source_meta=meta)
    else:
        if not engine.llama_cli():
            raise ValueError("llama.cpp is missing. Run ./download.sh")
        task = "describe" if spec.get("task") == "describe" else "suggest"
        job = new_job("assist", private, source=source, task=task, refs=[source],
                      prompt="Describe image" if task == "describe" else "Suggest edits", width=w, height=h)
    return enqueue([job])


def cancel(job_id):
    job = JOBS.get(job_id)
    if not job or job["state"] in ("done", "error", "cancelled"):
        return
    was_running = job["state"] in ("running", "starting")
    job.update(state="cancelled", stage="Cancelled")
    if was_running:
        if job.get("engine") == "warm":
            ENGINE.stop()   # sd-server can't stop mid-job; restarting is the only way
        else:
            ColdRun.cancel()


def move(job_id, direction):
    with LOCK:
        queued = [i for i in ORDER if JOBS[i]["state"] == "queued"]
        if job_id not in queued:
            return
        k = queued.index(job_id)
        j = k + (1 if direction > 0 else -1)
        if 0 <= j < len(queued):
            a, b = ORDER.index(queued[k]), ORDER.index(queued[j])
            ORDER[a], ORDER[b] = ORDER[b], ORDER[a]


# ---------------------------------------------------------------- gallery and private tray

def gallery():
    items = []
    for f in os.listdir(OUTPUTS):
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            p = os.path.join(OUTPUTS, f)
            items.append({"name": f, "mtime": os.path.getmtime(p), "meta": sidecar_of(f)})
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def delete_image(name):
    """Remove an image and everything that records it: settings sidecar, every log that mentions
    it, its queue entry, and uploaded sources or masks no other gallery image still uses."""
    removed = []

    def rm(p):
        if os.path.exists(p):
            os.remove(p)
            removed.append(os.path.relpath(p, ROOT))

    img = os.path.join(OUTPUTS, name)
    meta = sidecar_of(name)
    uses = list(meta.get("refs") or []) + ([meta["mask"]] if meta.get("mask") else [])
    rm(img)
    rm(img.rsplit(".", 1)[0] + ".json")

    needle = name.encode()
    for f in os.listdir(LOGS):
        p = os.path.join(LOGS, f)
        try:
            with open(p, "rb") as fh:
                if needle in fh.read():
                    rm(p)
        except OSError:
            pass

    still_used = set()
    for g in gallery():
        still_used.update(g["meta"].get("refs") or [])
        if g["meta"].get("mask"):
            still_used.add(g["meta"]["mask"])
    for r in uses:
        if r not in still_used:
            rm(os.path.join(INPUTS, r))

    drop_jobs(lambda j: j.get("output") == name)
    return removed


def private_items():
    with LOCK:
        jobs = [JOBS[i] for i in ORDER if JOBS[i].get("private") and JOBS[i]["state"] == "done" and JOBS[i].get("output")]
    return [{"name": j["output"], "meta": j.get("meta", {})} for j in reversed(jobs)
            if os.path.exists(os.path.join(PRIVATE, j["output"]))]


def keep_private(name):
    """Move a private result into the gallery. Private sources it depends on are copied to inputs/
    so its before/after and history keep working after the private tray is wiped."""
    name = safe_name(name)
    shutil.move(os.path.join(PRIVATE, name), os.path.join(OUTPUTS, name))
    job = next((j for j in JOBS.values() if j.get("output") == name), None)
    meta = job.get("meta", {}) if job else {}
    for r in (meta.get("refs") or []) + ([meta["mask"]] if meta.get("mask") else []):
        if is_private_file(r) and not os.path.exists(os.path.join(INPUTS, r)):
            shutil.copy(os.path.join(PRIVATE, r), os.path.join(INPUTS, r))
    if job:
        job["private"] = False
    write_sidecar(os.path.join(OUTPUTS, name), meta)
    return name


def discard_private(name=None):
    if name:
        p = os.path.join(PRIVATE, safe_name(name))
        if os.path.exists(p):
            os.remove(p)
        drop_jobs(lambda j: j.get("output") == name)
        return
    wipe_private()
    drop_jobs(lambda j: j.get("private") and j["state"] not in ("queued", "running", "starting"))


def save_upload(data, filename, private=False, kind="image"):
    b64 = data.split(",", 1)[1]
    ext = os.path.splitext(filename or "")[1].lower() or ".img"
    raw_path = os.path.join(TMP, "upload_" + uuid.uuid4().hex[:8] + ext)
    with open(raw_path, "wb") as f:
        f.write(base64.b64decode(b64))
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(filename or kind)[0])[:40] or kind
    name = "%s_%s%s.png" % (time.strftime("%Y%m%d-%H%M%S"), "mask_" if kind == "mask" else "", stem)
    out = os.path.join(PRIVATE if private else INPUTS, name)
    try:
        ok = to_png(raw_path, out, max_side=2048)  # handles HEIC, JPEG, WebP, TIFF
    except Exception:
        ok = False
    os.remove(raw_path)
    if not ok:
        raise ValueError("Could not read that image format")
    w, h = image_size(out)
    return {"name": name, "width": w, "height": h, "private": private}


def zip_of(names):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for n in names:
            n = safe_name(n)
            p = os.path.join(OUTPUTS, n) if os.path.exists(os.path.join(OUTPUTS, n)) else os.path.join(PRIVATE, n)
            if os.path.exists(p):
                z.write(p, n)
    return buf.getvalue()


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_bytes(self, body, ctype, code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj).encode(), "application/json", code)

    def send_file(self, path):
        if not os.path.isfile(path):
            return self.send_json({"error": "not found"}, 404)
        ext = path.rsplit(".", 1)[-1].lower()
        ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
                 "html": "text/html; charset=utf-8"}.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            self.send_bytes(f.read(), ctype)

    def body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                return self.send_file(os.path.join(STUDIO, "index.html"))
            if path == "/api/state":
                with LOCK:
                    jobs = [public(JOBS[i]) for i in ORDER[-60:]]
                return self.send_json({
                    "jobs": jobs, "calib": load_calib(), "paused": QUEUE["paused"],
                    "private_mode": PRIVATE_MODE["on"], "engine_warm": ENGINE.running,
                    "turbo": engine.turbo_available(), "upscaler": engine.upscaler_available(),
                    "assistant": bool(engine.llama_cli()), "settings": load_settings(),
                    "samplers": SAMPLERS, "schedulers": SCHEDULERS})
            if path == "/api/gallery":
                return self.send_json(gallery())
            if path == "/api/private":
                return self.send_json(private_items())
            if path == "/api/library":
                return self.send_json(load_library())
            if path.startswith("/outputs/"):
                return self.send_file(os.path.join(OUTPUTS, safe_name(path[9:])))
            if path.startswith("/private/"):
                return self.send_file(os.path.join(PRIVATE, safe_name(path[9:])))
            if path.startswith("/ref/"):
                return self.send_file(ref_path(safe_name(path[5:])))
            if path.startswith("/preview/"):
                return self.send_file(os.path.join(TMP, safe_name(path[9:]) + "_preview.png"))
        except ValueError:
            return self.send_json({"error": "bad path"}, 400)
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            b = self.body()
            if path == "/api/jobs":
                return self.send_json({"ids": submit(b)})
            if path == "/api/upload":
                private = PRIVATE_MODE["on"] or bool(b.get("private"))
                return self.send_json(save_upload(b["data"], b.get("filename"), private, b.get("kind", "image")))
            if path == "/api/private/mode":
                PRIVATE_MODE["on"] = bool(b.get("on"))
                return self.send_json({"on": PRIVATE_MODE["on"]})
            if path == "/api/private/keep":
                return self.send_json({"name": keep_private(b["name"])})
            if path == "/api/private/discard":
                discard_private(b.get("name"))
                return self.send_json({"ok": True})
            if path == "/api/queue/pause":
                QUEUE["paused"] = bool(b.get("paused"))
                WAKE.set()
                return self.send_json({"paused": QUEUE["paused"]})
            if path == "/api/clear":
                drop_jobs(lambda j: j["state"] in ("done", "error", "cancelled") and not j.get("private"))
                return self.send_json({"ok": True})
            if path == "/api/settings":
                s = load_settings()
                if "idle_minutes" in b:
                    s["idle_minutes"] = max(1, min(120, int(b["idle_minutes"])))
                write_json(SETTINGS, s)
                apply_settings(s)
                return self.send_json(s)
            if path == "/api/engine/stop":
                ENGINE.stop()
                return self.send_json({"ok": True})
            if path == "/api/library":
                lib = load_library()
                if "presets" in b:
                    lib["presets"] = {str(k)[:40]: v for k, v in b["presets"].items()}
                if "favorites" in b:
                    lib["favorites"] = [str(p)[:2000] for p in b["favorites"]][:200]
                write_json(LIBRARY, lib)
                return self.send_json(lib)
            if path == "/api/zip":
                data = zip_of(b.get("names") or [])
                return self.send_bytes(data, "application/zip", extra={
                    "Content-Disposition": 'attachment; filename="qwen-images-%s.zip"' % time.strftime("%Y%m%d-%H%M%S")})
            m = re.match(r"^/api/jobs/(\w+)/(cancel|up|down)$", path)
            if m:
                if m.group(2) == "cancel":
                    cancel(m.group(1))
                else:
                    move(m.group(1), -1 if m.group(2) == "up" else 1)
                return self.send_json({"ok": True})
        except (ValueError, KeyError) as e:
            return self.send_json({"error": str(e)}, 400)
        self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/api/gallery/"):
            try:
                name = safe_name(path[13:])
            except ValueError:
                return self.send_json({"error": "bad name"}, 400)
            return self.send_json({"removed": delete_image(name)})
        self.send_json({"error": "not found"}, 404)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7860
    wipe_tmp()
    apply_settings(load_settings())
    threading.Thread(target=worker, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    def shutdown(*_):
        ColdRun.cancel()
        ENGINE.stop()
        wipe_private()
        os._exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    print("Qwen-Image Studio running at http://127.0.0.1:%d  (Ctrl+C to stop)" % port, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
