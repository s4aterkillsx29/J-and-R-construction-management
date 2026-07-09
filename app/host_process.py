"""Track and stop the local JRC network server process."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
PID_FILE = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser() / "host_server.pid"
PORT_FILE = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser() / "network_server_settings.json"


def write_host_pid(pid: int) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(int(pid)), encoding="ascii")


def read_host_pid() -> int | None:
    try:
        if PID_FILE.exists():
            return int(PID_FILE.read_text(encoding="ascii").strip())
    except Exception:
        pass
    return None


def clear_host_pid() -> None:
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return str(pid) in (result.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_host_port() -> int:
    try:
        if PORT_FILE.exists():
            data = json.loads(PORT_FILE.read_text(encoding="utf-8"))
            return int(data.get("port") or data.get("last_port") or 8765)
    except Exception:
        pass
    try:
        from app.runtime_utils import load_port

        return int(load_port() or 8765)
    except Exception:
        pass
    return int(os.environ.get("JRC_PORT", "8765"))


def _request_graceful_shutdown(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/api/host/prepare-shutdown"
    try:
        req = urllib.request.Request(
            url,
            method="POST",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _run_local_shutdown_safety_net() -> None:
    """Checkpoint DB and backup even if the host process cannot run atexit."""
    try:
        from app.server_lifecycle import on_server_shutdown

        on_server_shutdown(graceful=True)
    except Exception:
        pass


def stop_host_process() -> tuple[bool, str]:
    pid = read_host_pid()
    if not pid:
        return False, "No host process ID recorded."
    if not is_pid_running(pid):
        clear_host_pid()
        return True, "Host process was already stopped."
    port = _read_host_port()
    graceful = _request_graceful_shutdown(port)
    if not graceful:
        _run_local_shutdown_safety_net()
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T"],
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for _ in range(16):
                if not is_pid_running(pid):
                    break
                time.sleep(0.5)
            if is_pid_running(pid):
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        else:
            os.kill(pid, 15)
            for _ in range(16):
                if not is_pid_running(pid):
                    break
                time.sleep(0.5)
            if is_pid_running(pid):
                os.kill(pid, 9)
        clear_host_pid()
        detail = "Data checkpointed, logs archived, and backup saved."
        if not graceful:
            detail = "Host stopped — local safety backup ran before stop."
        return True, f"Stopped host process (PID {pid}). {detail}"
    except Exception as exc:
        return False, f"Could not stop host: {exc}"
