"""Track and stop the local JRC network server process."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
PID_FILE = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser() / "host_server.pid"


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


def stop_host_process() -> tuple[bool, str]:
    pid = read_host_pid()
    if not pid:
        return False, "No host process ID recorded."
    if not is_pid_running(pid):
        clear_host_pid()
        return True, "Host process was already stopped."
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.kill(pid, 15)
        clear_host_pid()
        return True, f"Stopped host process (PID {pid})."
    except Exception as exc:
        return False, f"Could not stop host: {exc}"
