"""Share the studio over a Cloudflare Quick Tunnel.

The tunnel never points at the main studio port. While sharing, a second listener runs on
127.0.0.1 and cloudflared forwards to it. Every request on that listener has to pass the key
gate (see RemoteGate in server.py), and in anonymous mode only the anonymous page and its API
are reachable. Nothing here writes to disk: cloudflared gets a throwaway HOME under studio/tmp,
and its log is read from a pipe only to find the link.
"""
import hmac
import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time

import engine

CLOUDFLARED = os.path.join(engine.BIN, "cloudflared")
CF_HOME = os.path.join(engine.STUDIO, "tmp", "cloudflared-home")
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
SESSION_IDLE = 30 * 60   # a visitor counts as active for 30 minutes after their last request


def available():
    return os.path.exists(CLOUDFLARED)


class Share:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "off"         # off, starting, on, error
        self.mode = None            # "anon" or "full"
        self.url = None
        self.key = None
        self.error = None
        self.started = None
        self.proc = None            # cloudflared
        self.caffeinate = None      # keeps the Mac awake while sharing
        self.listener = None        # the tunnel-only HTTP server
        self.sessions = {}          # session id -> last seen
        self.on_stop = []           # callbacks, e.g. wiping anonymous results
        self.stopping = False

    # -------------------------------------------------- state

    def link(self):
        return "%s/k/%s" % (self.url, self.key) if self.url and self.key else None

    def visitors(self):
        now = time.time()
        return sum(1 for t in self.sessions.values() if now - t < SESSION_IDLE)

    def state(self):
        return {"status": self.status, "mode": self.mode, "link": self.link() if self.status == "on" else None,
                "error": self.error, "visitors": self.visitors(), "available": available(),
                "since": self.started}

    def key_ok(self, key):
        return bool(self.key and key) and hmac.compare_digest(self.key, key)

    def touch(self, session):
        self.sessions[session] = time.time()

    # -------------------------------------------------- lifecycle

    def start(self, mode, make_listener):
        """make_listener() returns a started ThreadingHTTPServer bound to 127.0.0.1:0."""
        with self.lock:
            if self.status in ("starting", "on"):
                if mode != self.mode:
                    self.mode = mode            # switching mode keeps the same link
                return self.state()
            if not available():
                self.status, self.error = "error", "cloudflared is missing. Run ./download.sh"
                return self.state()
            self.status, self.mode, self.error, self.stopping = "starting", mode, None, False
            self.key = secrets.token_urlsafe(32)
            self.sessions = {}
            self.url = None
            self.listener = make_listener()
        threading.Thread(target=self._run, daemon=True).start()
        return self.state()

    def _run(self):
        port = self.listener.server_address[1]
        shutil.rmtree(CF_HOME, ignore_errors=True)
        os.makedirs(CF_HOME)
        env = dict(os.environ, HOME=CF_HOME)
        try:
            self.proc = subprocess.Popen(
                [CLOUDFLARED, "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:%d" % port],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=CF_HOME, start_new_session=True)
        except OSError as e:
            return self._fail("Could not start cloudflared: %s" % e)
        # keep reading the log so the pipe never fills up; only the link is kept
        found, registered = threading.Event(), threading.Event()
        proc = self.proc

        def read():
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace")
                m = URL_RE.search(line)
                if m and not self.url:
                    self.url = m.group(0)
                    found.set()
                if "Registered tunnel connection" in line:
                    registered.set()
            # cloudflared exited: if nobody asked it to, say so instead of showing a dead link
            if not self.stopping and self.proc is proc:
                self._fail("The tunnel closed unexpectedly (network change or sleep). Start sharing again.")
        threading.Thread(target=read, daemon=True).start()
        if not found.wait(45):
            return self._fail("Cloudflare didn't return a link. Check the internet connection and try again.")
        if not registered.wait(30):
            return self._fail("The tunnel didn't connect to Cloudflare. Try again in a minute.")
        try:
            self.caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(self.proc.pid)],
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.caffeinate = None
        # The new trycloudflare name needs a few seconds to reach DNS. Don't look it up from this Mac
        # before then: macOS would cache the "not found" answer and the link would fail here for minutes.
        time.sleep(6)
        if self.status == "starting":
            self.status, self.started = "on", time.time()

    def _fail(self, message):
        self.stop()
        self.status, self.error = "error", message

    def stop(self):
        self.stopping = True
        with self.lock:
            for p in (self.proc, self.caffeinate):
                if p and p.poll() is None:
                    try:
                        os.killpg(p.pid, signal.SIGTERM) if p is self.proc else p.terminate()
                        p.wait(timeout=5)
                    except Exception:
                        try:
                            p.kill()
                        except Exception:
                            pass
            self.proc = self.caffeinate = None
            if self.listener:
                threading.Thread(target=self.listener.shutdown, daemon=True).start()
                self.listener = None
            self.status, self.mode, self.url, self.key, self.started = "off", None, None, None, None
            self.sessions = {}
            shutil.rmtree(CF_HOME, ignore_errors=True)
        for cb in self.on_stop:
            try:
                cb()
            except Exception:
                pass


SHARE = Share()
