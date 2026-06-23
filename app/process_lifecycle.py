"""Track JRC background processes and clean up when windows close."""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
REGISTRY_PATH = BASE_DIR / "data" / "jrc_process_registry.json"
START_CENTER_LOCK = BASE_DIR / "data" / "jrc_start_center.lock"
_INSTALL_MARKER = str(BASE_DIR).lower().replace("/", "\\")


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _read_registry() -> dict[str, Any]:
    try:
        if REGISTRY_PATH.exists():
            return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"processes": []}


def _write_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        REGISTRY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def is_alive(pid: int) -> bool:
    pid = int(pid or 0)
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=_no_window(),
            )
            text = (result.stdout or "").strip()
            return text and "No tasks" not in text and str(pid) in text
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_pid(pid: int, force: bool = True) -> bool:
    pid = int(pid or 0)
    if pid <= 0 or not is_alive(pid):
        return True
    try:
        if os.name == "nt":
            args = ["taskkill", "/PID", str(pid), "/T"]
            if force:
                args.append("/F")
            subprocess.run(args, capture_output=True, timeout=12, creationflags=_no_window())
        else:
            os.kill(pid, 9)
        return not is_alive(pid)
    except Exception:
        return not is_alive(pid)


def _is_jrc_network_server_command(command_line: str) -> bool:
    cl = (command_line or "").lower().replace("/", "\\")
    if "network_server" not in cl:
        return False
    return _INSTALL_MARKER in cl or "j_and_r_construction_manager" in cl or "jacobconstruction" in cl


def find_network_server_pids() -> list[int]:
    pids: list[int] = []
    if os.name != "nt":
        return pids
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
            "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=_no_window(),
        )
        raw = (result.stdout or "").strip()
        if not raw:
            return pids
        data = json.loads(raw)
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            cmd = str(row.get("CommandLine") or "")
            if _is_jrc_network_server_command(cmd):
                pids.append(int(row["ProcessId"]))
    except Exception:
        pass
    return sorted(set(pids))


def register_process(pid: int, kind: str, owner_pid: int | None = None, note: str = "") -> None:
    pid = int(pid or 0)
    if pid <= 0:
        return
    reg = _read_registry()
    processes = [p for p in reg.get("processes", []) if int(p.get("pid", 0)) != pid]
    processes.append(
        {
            "pid": pid,
            "kind": kind,
            "owner_pid": int(owner_pid or os.getpid()),
            "note": note,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    reg["processes"] = processes
    _write_registry(reg)


def unregister_process(pid: int) -> None:
    pid = int(pid or 0)
    reg = _read_registry()
    reg["processes"] = [p for p in reg.get("processes", []) if int(p.get("pid", 0)) != pid]
    _write_registry(reg)


def prune_registry() -> None:
    reg = _read_registry()
    reg["processes"] = [p for p in reg.get("processes", []) if is_alive(int(p.get("pid", 0)))]
    _write_registry(reg)


def start_center_lock_pid() -> int:
    try:
        if START_CENTER_LOCK.exists():
            data = json.loads(START_CENTER_LOCK.read_text(encoding="utf-8"))
            return int(data.get("pid", 0))
    except Exception:
        pass
    return 0


def acquire_start_center_lock() -> tuple[bool, str]:
    my_pid = os.getpid()
    existing = start_center_lock_pid()
    if existing and existing != my_pid and is_alive(existing):
        return False, "Start Center is already open on this computer."
    START_CENTER_LOCK.parent.mkdir(parents=True, exist_ok=True)
    START_CENTER_LOCK.write_text(
        json.dumps({"pid": my_pid, "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}),
        encoding="utf-8",
    )
    atexit.register(release_start_center_lock)
    return True, ""


def release_start_center_lock() -> None:
    try:
        if START_CENTER_LOCK.exists():
            data = json.loads(START_CENTER_LOCK.read_text(encoding="utf-8"))
            if int(data.get("pid", 0)) == os.getpid():
                START_CENTER_LOCK.unlink(missing_ok=True)
    except Exception:
        try:
            START_CENTER_LOCK.unlink(missing_ok=True)
        except Exception:
            pass


def stop_network_hosts(except_pid: int | None = None) -> list[int]:
    stopped: list[int] = []
    for pid in find_network_server_pids():
        if except_pid and pid == int(except_pid):
            continue
        if stop_pid(pid):
            stopped.append(pid)
            unregister_process(pid)
    return stopped


def stop_owned_processes(owner_pid: int | None = None, kinds: set[str] | None = None) -> list[int]:
    owner_pid = int(owner_pid or os.getpid())
    stopped: list[int] = []
    reg = _read_registry()
    for entry in list(reg.get("processes", [])):
        pid = int(entry.get("pid", 0))
        kind = str(entry.get("kind", ""))
        if int(entry.get("owner_pid", 0)) != owner_pid:
            continue
        if kinds and kind not in kinds:
            continue
        if stop_pid(pid):
            stopped.append(pid)
            unregister_process(pid)
    return stopped


def cleanup_orphan_hosts() -> list[int]:
    """Stop network servers left running after Start Center was closed."""
    lock_pid = start_center_lock_pid()
    if lock_pid and is_alive(lock_pid):
        return []
    return stop_network_hosts()


def prepare_for_new_host() -> list[int]:
    """Ensure only one local web host runs for this install."""
    prune_registry()
    return stop_network_hosts()


def startup_cleanup() -> None:
    prune_registry()
    lock_pid = start_center_lock_pid()
    if lock_pid and not is_alive(lock_pid):
        release_start_center_lock()
    cleanup_orphan_hosts()


def shutdown_start_center(stop_host: bool = True, owner_pid: int | None = None) -> None:
    owner_pid = int(owner_pid or os.getpid())
    if stop_host:
        stop_owned_processes(owner_pid, kinds={"network_server"})
    if start_center_lock_pid() == owner_pid:
        release_start_center_lock()
    prune_registry()


def track_popen(proc: subprocess.Popen | None, kind: str, note: str = "") -> subprocess.Popen | None:
    if proc is None or proc.pid is None:
        return proc
    register_process(proc.pid, kind, owner_pid=os.getpid(), note=note)
    return proc


def cli_cleanup() -> int:
    stopped = cleanup_orphan_hosts()
    prune_registry()
    print(f"Cleaned {len(stopped)} orphan host process(es).")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_cleanup())
