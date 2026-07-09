"""Unified server start/stop/status/restart/sessions/log tail for JRC host."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = BASE_DIR / "logs"
HOST_LOG = LOG_DIR / "shared_host_last.log"
DEFAULT_PORT = int(os.environ.get("JRC_PORT", "8765"))


def _data_dir(base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir or BASE_DIR).resolve()
    return Path(os.environ.get("JRC_DATA_DIR", str(root / "data"))).expanduser()


def _read_port(base_dir: Optional[Path] = None) -> int:
    fp = _data_dir(base_dir) / "network_server_settings.json"
    try:
        if fp.exists():
            data = json.loads(fp.read_text(encoding="utf-8"))
            return int(data.get("port") or data.get("last_port") or DEFAULT_PORT)
    except Exception:
        pass
    try:
        from app.runtime_utils import get_saved_port

        return int(get_saved_port())
    except Exception:
        pass
    return DEFAULT_PORT


def _local_url(path: str, port: Optional[int] = None) -> str:
    p = int(port or _read_port())
    if not path.startswith("/"):
        path = "/" + path
    return f"http://127.0.0.1:{p}{path}"


def _http_json(url: str, method: str = "GET", timeout: float = 2.0) -> tuple[bool, Dict[str, Any]]:
    try:
        data = b"{}"
        req = urllib.request.Request(
            url,
            method=method,
            data=data if method != "GET" else None,
            headers={"Content-Type": "application/json"} if method != "GET" else {},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(65536).decode("utf-8", errors="replace")
            return True, json.loads(body) if body.strip().startswith("{") else {"raw": body[:500]}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(4096).decode("utf-8", errors="replace")
            payload = json.loads(body) if body.strip().startswith("{") else {"error": body[:200]}
        except Exception:
            payload = {"error": str(exc)}
        payload["http_status"] = exc.code
        return False, payload
    except Exception as exc:
        return False, {"error": str(exc)}


def is_running(port: Optional[int] = None) -> bool:
    p = int(port or _read_port())
    ok, data = _http_json(_local_url("/api/health", p), timeout=1.0)
    return ok and data.get("status") == "ok"


def get_status(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    port = _read_port(base_dir)
    running = is_running(port)
    pid = None
    try:
        from app.host_process import read_host_pid

        pid = read_host_pid()
    except Exception:
        pass
    lan_ip = "127.0.0.1"
    cloud_url = ""
    sessions_count = 0
    version = ""
    uptime = ""
    if running:
        ok, data = _http_json(_local_url("/api/local-host-admin", port), timeout=1.5)
        if ok:
            lan_ip = str(data.get("lan_ip") or lan_ip)
            cloud_url = str(data.get("cloud_url") or "")
            sessions_count = int(data.get("active_sessions") or 0)
            version = str(data.get("version") or "")
            last_boot = str(data.get("last_boot") or "")
            if last_boot:
                uptime = last_boot
    try:
        from app.host_role_registry import get_host_strategy, get_pc_role, host_role_display

        pc_role = get_pc_role(base_dir)
        host_strategy = get_host_strategy(base_dir)
        role_display = host_role_display(base_dir)
    except Exception:
        pc_role = "owner_office"
        host_strategy = "local_embedded"
        role_display = "Office PC"
    return {
        "ok": True,
        "running": running,
        "port": port,
        "pid": pid,
        "lan_ip": lan_ip,
        "lan_url": f"http://{lan_ip}:{port}",
        "local_url": _local_url("/", port),
        "cloud_url": cloud_url,
        "sessions_count": sessions_count,
        "version": version,
        "uptime": uptime,
        "pc_role": pc_role,
        "host_strategy": host_strategy,
        "role_display": role_display,
        "log_path": str(HOST_LOG),
    }


def get_sessions(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    port = _read_port(base_dir)
    if not is_running(port):
        try:
            from app.start_center import read_local_sessions

            return read_local_sessions()
        except Exception:
            return []
    ok, data = _http_json(_local_url("/api/local-host-admin", port), timeout=1.5)
    if ok:
        return list(data.get("sessions") or [])
    return []


def tail_logs(lines: int = 100, log_path: Optional[Path] = None) -> str:
    fp = Path(log_path or HOST_LOG)
    if not fp.exists():
        return f"No log file yet: {fp}"
    try:
        data = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(data[-max(1, int(lines)) :])
    except Exception as exc:
        return f"Could not read log: {exc}"


def _launch_server(base_dir: Optional[Path] = None, port: Optional[int] = None) -> tuple[bool, str, Optional[int]]:
    root = Path(base_dir or BASE_DIR)
    p = int(port or _read_port(root))
    LOG_DIR.mkdir(exist_ok=True)
    log_path = HOST_LOG
    python = root / ".venv" / "Scripts" / "python.exe"
    py = str(python) if python.exists() else sys.executable
    env = os.environ.copy()
    env["JRC_PORT"] = str(p)
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as log:
            log.write(f"\n--- server_control start {datetime.now().isoformat()} port={p} ---\n")
            proc = subprocess.Popen(
                [py, "-m", "app.network_server"],
                cwd=str(root),
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        try:
            from app.host_process import write_host_pid

            write_host_pid(proc.pid)
        except Exception:
            pass
        deadline = time.time() + 25.0
        while time.time() < deadline:
            if is_running(p):
                return True, f"Host started on port {p}", p
            time.sleep(0.75)
        return False, f"Host process started but /api/health did not respond on port {p}", p
    except Exception as exc:
        return False, str(exc), p


def start_server(base_dir: Optional[Path] = None, *, force: bool = False) -> Dict[str, Any]:
    root = Path(base_dir or BASE_DIR)
    port = _read_port(root)
    if is_running(port) and not force:
        return {"ok": True, "running": True, "started": False, "message": "Host already running", "port": port}
    if not force:
        try:
            from app.host_role_registry import pre_start_host_allowed

            proceed, msg = pre_start_host_allowed(root)
            if not proceed:
                return {"ok": False, "running": False, "started": False, "blocked": True, "message": msg, "port": port}
        except Exception:
            pass
    ok, msg, used_port = _launch_server(root, port)
    return {
        "ok": ok,
        "running": ok,
        "started": ok,
        "message": msg,
        "port": used_port or port,
    }


def stop_server() -> Dict[str, Any]:
    if not is_running():
        try:
            from app.host_process import stop_host_process, read_host_pid

            if read_host_pid():
                ok, msg = stop_host_process()
                return {"ok": ok, "running": False, "message": msg}
        except Exception:
            pass
        return {"ok": True, "running": False, "message": "Host was not running"}
    try:
        from app.host_process import stop_host_process

        ok, msg = stop_host_process()
        return {"ok": ok, "running": is_running(), "message": msg}
    except Exception as exc:
        return {"ok": False, "running": is_running(), "message": str(exc)}


def restart_server(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    stop = stop_server()
    time.sleep(1.0)
    start = start_server(base_dir, force=True)
    return {
        "ok": start.get("ok", False),
        "running": start.get("running", False),
        "stop_message": stop.get("message", ""),
        "message": start.get("message", ""),
        "port": start.get("port"),
    }


def repair_database_lock(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Stop duplicate JRC processes, repair SQLite, restart host server (background)."""
    root = Path(base_dir or BASE_DIR).resolve()
    script_candidates = [
        root / "tools" / "FIX_HOST_DATABASE_LOCK.ps1",
        Path(__file__).resolve().parents[2] / "tools" / "FIX_HOST_DATABASE_LOCK.ps1",
        Path(os.environ.get("USERPROFILE", "")) / "projects" / "JRC-Construction-Office" / "tools" / "FIX_HOST_DATABASE_LOCK.ps1",
        Path(r"\\192.168.50.59\JRC-HOST-SETUP\HOST_SETUP_TOOLS\FIX_HOST_DATABASE_LOCK.ps1"),
    ]
    script = next((p for p in script_candidates if p.is_file()), None)
    if not script:
        return {"ok": False, "message": "FIX_HOST_DATABASE_LOCK.ps1 not found on host"}
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if os.name == "nt":
            flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        proc = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-FromApi",
            ],
            cwd=str(root),
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "ok": True,
            "message": "Database repair started in background. Host server may restart in ~30 seconds.",
            "pid": proc.pid,
            "script": str(script),
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def start_if_needed(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    status = get_status(base_dir)
    if status.get("running"):
        return {**status, "started": False, "message": "Host already running"}
    result = start_server(base_dir)
    merged = get_status(base_dir)
    merged.update(result)
    return merged


def allow_firewall() -> Dict[str, Any]:
    try:
        from app.runtime_utils import ensure_lan_firewall, lan_firewall_rule_exists

        if lan_firewall_rule_exists():
            return {"ok": True, "message": "LAN firewall rule already exists"}
        ok, msg = ensure_lan_firewall()
        return {"ok": ok, "message": msg}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def apply_power_24x7() -> Dict[str, Any]:
    """Apply 24/7 host power settings on this PC (elevates if script found)."""
    lines: List[str] = []
    script_candidates = [
        Path(r"C:\JRC-HOST-SHARE\HOST_SETUP_TOOLS\ENABLE_HOST_POWER_RECOVERY.ps1"),
        Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "HOST_LAPTOP_SETUP" / "HOST_SETUP_TOOLS" / "ENABLE_HOST_POWER_RECOVERY.ps1",
        Path(__file__).resolve().parents[1] / "tools" / "ENABLE_HOST_POWER_RECOVERY.ps1",
        Path(r"\\192.168.50.59\JRC-HOST-SETUP\HOST_SETUP_TOOLS\ENABLE_HOST_POWER_RECOVERY.ps1"),
        Path(r"\\100.95.109.11\JRC-HOST-SETUP\HOST_SETUP_TOOLS\ENABLE_HOST_POWER_RECOVERY.ps1"),
    ]
    script = next((p for p in script_candidates if p.exists()), None)
    if script:
        try:
            proc = subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{script}' -Wait",
                ],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            out, _ = proc.communicate(timeout=120)
            text = (out or b"").decode("utf-8", errors="replace").strip()
            return {
                "ok": proc.returncode == 0,
                "message": "Launched power recovery script (approve UAC on host if prompted)",
                "script": str(script),
                "output": text[-1500:],
            }
        except Exception as exc:
            lines.append(f"script launch failed: {exc}")

    cmds = [
        ["powercfg", "/change", "monitor-timeout-ac", "0"],
        ["powercfg", "/change", "standby-timeout-ac", "0"],
        ["powercfg", "/change", "standby-timeout-dc", "0"],
        ["powercfg", "/change", "hibernate-timeout-ac", "0"],
        ["powercfg", "/hibernate", "off"],
        ["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
    ]
    ok_all = True
    for cmd in cmds:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            line = f"{' '.join(cmd)} -> exit {proc.returncode}"
            if proc.stderr:
                line += f" ({proc.stderr.strip()[:80]})"
            lines.append(line)
            if proc.returncode != 0:
                ok_all = False
        except Exception as exc:
            lines.append(f"{' '.join(cmd)} -> {exc}")
            ok_all = False
    try:
        scheme = subprocess.check_output(["powercfg", "/getactivescheme"], text=True, timeout=10).strip()
        lines.append(f"Active scheme: {scheme}")
    except Exception as exc:
        lines.append(f"scheme read: {exc}")
    return {
        "ok": ok_all,
        "message": "Inline powercfg applied (some steps may need Administrator)",
        "output": "\n".join(lines),
    }


def _schedule_windows_power_action(
    action: str,
    delay_seconds: int = 60,
    comment: str = "",
) -> Dict[str, Any]:
    """Schedule Windows shutdown (/s) or reboot (/r) on this PC (needs Administrator)."""
    flag = "/r" if action == "reboot" else "/s"
    label = "restart" if action == "reboot" else "shutdown"
    sec = max(0, min(int(delay_seconds or 60), 600))
    if not comment:
        comment = f"JRC dedicated host {label} requested"
    try:
        proc = subprocess.run(
            [
                "shutdown",
                flag,
                "/t",
                str(sec),
                "/f",
                "/c",
                comment,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        msg = (proc.stdout or proc.stderr or "").strip()
        return {
            "ok": proc.returncode == 0,
            "action": action,
            "message": (
                f"Windows {label} scheduled in {sec} seconds"
                if proc.returncode == 0
                else f"{label} failed"
            ),
            "delay_seconds": sec,
            "output": msg,
            "cancel": "shutdown /a",
        }
    except Exception as exc:
        return {"ok": False, "action": action, "message": str(exc), "delay_seconds": sec}


def reboot_host_pc(delay_seconds: int = 60) -> Dict[str, Any]:
    """Schedule a Windows restart on this PC (dedicated host — needs Administrator)."""
    return _schedule_windows_power_action("reboot", delay_seconds)


def shutdown_host_pc(delay_seconds: int = 45) -> Dict[str, Any]:
    """Schedule a Windows shutdown on this PC (dedicated host — needs Administrator)."""
    return _schedule_windows_power_action(
        "shutdown",
        delay_seconds,
        "JRC dedicated host shutdown requested",
    )


def share_links(base_dir: Optional[Path] = None) -> Dict[str, str]:
    st = get_status(base_dir)
    base = st.get("lan_url") or _local_url("/", st.get("port"))
    base = str(base).rstrip("/")
    return {
        "mobile": f"{base}/mobile",
        "connect": f"{base}/connect",
        "register": f"{base}/register",
        "apply": f"{base}/apply",
        "login": f"{base}/login",
        "admin_server": f"{base}/admin/server",
    }


def _office_setup_script(name: str) -> Optional[Path]:
    candidates = [
        Path(rf"\\100.95.109.11\JRC-HOST-SETUP\HOST_SETUP_TOOLS\{name}"),
        Path(rf"\\192.168.50.59\JRC-HOST-SETUP\HOST_SETUP_TOOLS\{name}"),
        Path(rf"\\JRCONST\JRC-HOST-SETUP\HOST_SETUP_TOOLS\{name}"),
        Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "HOST_LAPTOP_SETUP" / "HOST_SETUP_TOOLS" / name,
        Path(r"C:\JRC-HOST-SHARE\HOST_SETUP_TOOLS") / name,
    ]
    return next((p for p in candidates if p.is_file()), None)


def bootstrap_remote_paths(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Run host remote-path + WiFi stable scripts from office share (elevated)."""
    root = Path(base_dir or BASE_DIR).resolve()
    scripts = [
        ("fix_remote_paths", "FIX_HOST_REMOTE_PATHS.ps1"),
        ("wifi_stable", "Enable-HostWiFiStable.ps1"),
        ("register_poll", "REGISTER_OFFICE_COMMAND_POLL.ps1"),
    ]
    launched: List[str] = []
    missing: List[str] = []
    for label, fname in scripts:
        script = _office_setup_script(fname)
        if not script:
            missing.append(fname)
            continue
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{script}' -Wait",
                ],
                cwd=str(root),
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            launched.append(f"{label}:{script}")
        except Exception as exc:
            missing.append(f"{fname} ({exc})")
    ok = bool(launched)
    return {
        "ok": ok,
        "message": "Bootstrap launched on host (approve UAC if prompted)" if ok else "No setup scripts found on office share",
        "launched": launched,
        "missing": missing,
    }
