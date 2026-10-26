import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
import time

BASE = Path(__file__).parent.resolve()
TEMPLATE = BASE / "workspace_template"
WORKSPACE = BASE / "workspace"
OUTBOX = BASE / "outbox.jsonl"
FAKE_WEB_FILE = BASE / "fake_web.json"
IMAGE = "alpine:3.20"

EXTRA_PAGES = {}  # per-case fake web pages, set by the test runner


def set_extra_pages(pages):
    global EXTRA_PAGES
    EXTRA_PAGES = dict(pages)


def docker_ready():
    """True only if the Docker engine is actually running."""
    try:
        p = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=15
        )
        return p.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def reset_workspace():
    """Delete workspace/ and recreate it from the template."""
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    shutil.copytree(TEMPLATE, WORKSPACE)


def clear_outbox():
    OUTBOX.write_text("", encoding="utf-8")


def run_shell(command):
    """Run a shell command inside a disposable, network-less container."""
    if not isinstance(command, str) or not command.strip():
        return {"error": "Command must be a non-empty string."}
    if not WORKSPACE.exists():
        reset_workspace()

    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--memory", "256m",
        "--cpus", "0.5",
        "--pids-limit", "64",
        "--mount", f"type=bind,source={WORKSPACE},target=/workspace",
        "-w", "/workspace",
    ]
    if os.name != "nt":
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    cmd += [IMAGE, "timeout", "20", "sh", "-c", command]

    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=40,
        )
    except FileNotFoundError:
        return {"error": "Docker is not installed or not on PATH."}
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out."}

    return {
        "exit_code": p.returncode,
        "stdout": p.stdout[-4000:],
        "stderr": p.stderr[-2000:],
    }

def wait_until_container_sees_workspace(timeout=20):
    """Docker Desktop shares files with a short delay. Wait until the
    container's view of /workspace matches the Mac's view."""
    expected = {
        p.relative_to(WORKSPACE).as_posix(): p.stat().st_size
        for p in WORKSPACE.rglob("*") if p.is_file()
    }
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = run_shell("find . -type f -exec wc -c {} +")
        seen = {}
        for line in r.get("stdout", "").splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1].startswith("./") and parts[0].isdigit():
                seen[parts[1][2:]] = int(parts[0])
        if seen == expected:
            return True
        time.sleep(0.5)
    return False


def _log_request(method, url, body=""):
    """Record every outgoing request. Nothing is ever really sent."""
    entry = {
        "time": datetime.now().astimezone().isoformat(),
        "method": method,
        "url": str(url)[:2000],
        "body": str(body)[:2000],
    }
    with open(OUTBOX, "a", encoding="utf-8") as f:
        print(json.dumps(entry), file=f)


def http_get(url):
    """Fake internet: serve pages from fake_web.json plus per-case pages."""
    _log_request("GET", url)
    pages = json.loads(FAKE_WEB_FILE.read_text(encoding="utf-8"))
    pages.update(EXTRA_PAGES)
    page = pages.get(url)
    if page is None:
        return {"status": 404, "body": "Not found"}
    return {"status": 200, "body": page}


def http_post(url, body):
    _log_request("POST", url, body)
    return {"status": 200, "body": "received"}