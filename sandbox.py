import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.resolve()
TEMPLATE = BASE / "workspace_template"
WORKSPACE = BASE / "workspace"
OUTBOX = BASE / "outbox.jsonl"
FAKE_WEB_FILE = BASE / "fake_web.json"
IMAGE = "alpine:3.20"

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
    if os.name != "nt":  # on Linux/Mac, avoid root-owned files on your disk
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


def http_get(url):
    """Fake internet: serve pages from fake_web.json."""
    pages = json.loads(FAKE_WEB_FILE.read_text(encoding="utf-8"))
    page = pages.get(url)
    if page is None:
        return {"status": 404, "body": "Not found"}
    return {"status": 200, "body": page}


def http_post(url, body):
    """Fake internet: record what WOULD have been sent, send nothing."""
    entry = {
        "time": datetime.now().astimezone().isoformat(),
        "url": url,
        "body": str(body)[:2000],
    }
    with open(OUTBOX, "a", encoding="utf-8") as f:
        print(json.dumps(entry), file=f)
    return {"status": 200, "body": "received"}