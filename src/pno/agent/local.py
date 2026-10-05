"""The offline AI: llama.cpp's llama-server running a small model on this PC (OpenAI-compatible, with tool calling).

The runtime ships inside the Windows package (runtime/llama). The model is downloaded once from Hugging Face from
Settings, or an existing .gguf file is chosen. After that nothing needs the internet and no data leaves the PC.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

from ..paths import data_dir, resource
from . import llm
from .llm import ssl_ctx

PORT = 18181
MODEL = {"name": "Qwen 2.5 3B Instruct", "repo": "bartowski/Qwen2.5-3B-Instruct-GGUF",
         "file": "Qwen2.5-3B-Instruct-Q4_K_M.gguf", "gb": 1.9}


def models_dir() -> Path:
    p = data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runtime_dir() -> Path:
    p = data_dir() / "runtime"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _exe(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def find_runtime() -> Path | None:
    for base in (resource("runtime", "llama"), runtime_dir() / "llama"):
        if base.exists():
            hits = list(base.rglob(_exe("llama-server")))
            if hits:
                return hits[0]
    w = shutil.which("llama-server")
    return Path(w) if w else None


def model_path(db) -> str | None:
    linked = db.get_setting("offline_model", "")
    if linked and Path(linked).exists():
        return linked
    p = models_dir() / MODEL["file"]
    return str(p) if p.exists() else None


class Downloads:
    def __init__(self):
        self.jobs: dict[str, dict] = {}

    def start(self, url: str, dest: Path, name: str, after=None) -> str:
        for j in self.jobs.values():
            if j["dest"] == str(dest) and j["status"] == "running":
                return j["id"]
        jid = uuid.uuid4().hex[:8]
        job = {"id": jid, "name": name, "dest": str(dest), "total": 0, "done": 0, "status": "running", "error": ""}
        self.jobs[jid] = job
        threading.Thread(target=self._run, args=(job, url, after), daemon=True).start()
        return jid

    def _run(self, job, url, after):
        dest = Path(job["dest"])
        part = dest.with_suffix(dest.suffix + ".part")
        try:
            have = part.stat().st_size if part.exists() else 0
            headers = {"User-Agent": "PNO/1.0"}
            if have:
                headers["Range"] = f"bytes={have}-"
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60, context=ssl_ctx()) as r:
                total = int(r.headers.get("Content-Length") or 0)
                if r.status == 206:
                    job["total"] = have + total
                else:
                    have, job["total"] = 0, total
                job["done"] = have
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        job["done"] += len(chunk)
            part.replace(dest)
            if after:
                after(dest)
            job["status"] = "done"
        except Exception as e:
            job["status"], job["error"] = "error", str(e)

    def list(self) -> list[dict]:
        return [dict(j, pct=round(j["done"] / j["total"] * 100, 1) if j["total"] else 0) for j in self.jobs.values()]


DOWNLOADS = Downloads()


def download_model() -> str:
    url = f"https://huggingface.co/{MODEL['repo']}/resolve/main/{MODEL['file']}?download=true"
    return DOWNLOADS.start(url, models_dir() / MODEL["file"], MODEL["name"])


def install_runtime() -> str:
    """Fetch the CPU build of llama.cpp for this PC (only needed when running from source)."""
    with urllib.request.urlopen(urllib.request.Request("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
                                                       headers={"User-Agent": "PNO/1.0"}), timeout=30, context=ssl_ctx()) as r:
        rel = json.loads(r.read().decode("utf-8"))
    sysname = platform.system()
    pat = re.compile(r"bin-win-cpu-x64\.zip$" if sysname == "Windows" else r"bin-macos-arm64\.zip$" if sysname == "Darwin"
                     else r"bin-ubuntu-x64\.zip$")
    asset = next((a for a in rel.get("assets") or [] if pat.search(a["name"])), None)
    if not asset:
        raise RuntimeError("No llama.cpp build was found for this computer.")
    target = runtime_dir() / "llama"

    def unpack(p: Path):
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(p) as z:
            z.extractall(target)
        p.unlink(missing_ok=True)
        if sys.platform != "win32":
            for f in target.rglob("*"):
                if f.is_file() and not f.suffix:
                    f.chmod(0o755)

    return DOWNLOADS.start(asset["browser_download_url"], runtime_dir() / asset["name"], f"Offline runtime {rel.get('tag_name')}", unpack)


class Server:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.model = ""
        self.log: list[str] = []
        self._lock = threading.Lock()

    def ready(self) -> bool:
        if not self.proc or self.proc.poll() is not None:
            return False
        try:
            with llm.urlopen(f"http://127.0.0.1:{PORT}/health", 2) as r:
                return r.status == 200
        except Exception:
            return False

    def ensure(self, model: str, wait: float = 120) -> bool:
        """Start the server if needed and wait until the model is loaded."""
        with self._lock:
            if self.proc and self.proc.poll() is None and self.model == model:
                pass
            else:
                exe = find_runtime()
                if not exe:
                    raise RuntimeError("The offline AI runtime is missing. Use Settings → AI → Set up offline AI.")
                self.stop()
                cores = os.cpu_count() or 4
                threads = max(2, cores // 2) if cores >= 8 else max(2, cores - 1)
                args = [str(exe), "-m", model, "--host", "127.0.0.1", "--port", str(PORT), "-c", "8192", "--jinja",
                        "-t", str(threads), "-np", "1"]
                flags = 0x08000000 if sys.platform == "win32" else 0
                self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(exe.parent),
                                             creationflags=flags, text=True, encoding="utf-8", errors="replace")
                self.model = model
                threading.Thread(target=self._pump, daemon=True).start()
        end = time.time() + wait
        while time.time() < end:
            if self.ready():
                return True
            if self.proc is None or self.proc.poll() is not None:
                raise RuntimeError("The offline AI could not start: " + " ".join(self.log[-3:]))
            time.sleep(0.5)
        return False

    def _pump(self):
        p = self.proc
        if p and p.stdout:
            for line in p.stdout:
                self.log = (self.log + [line.rstrip()[:200]])[-200:]

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


SERVER = Server()
