"""Remote host PC control — internet access status, probes, admin settings.

OS-level control (RustDesk/RDP/Tailscale) runs via HOST-PC-ADMIN PowerShell on the
office master PC. This module surfaces status and settings inside JRC Manager /admin.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]

SETTING_KEYS = (
    "remote_host_lan_ip",
    "remote_host_tailscale_ip",
    "remote_host_tailscale_name",
    "remote_host_rustdesk_id",
    "remote_host_pc_name",
    "remote_host_mac",
    "remote_pc_last_probe_at",
    "remote_pc_last_probe_json",
    "remote_pc_last_verify_at",
    "remote_pc_last_verify_json",
)


def _default_host_lan_ip() -> str:
    return (os.environ.get("JRC_DEFAULT_HOST_LAN_IP") or "192.168.50.83").strip()


def get_remote_pc_settings(get_app_setting, set_app_setting=None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key in SETTING_KEYS:
        out[key] = (get_app_setting(key, "") or "").strip()
    if not out.get("remote_host_lan_ip"):
        out["remote_host_lan_ip"] = _default_host_lan_ip()
    if not out.get("remote_host_pc_name"):
        out["remote_host_pc_name"] = "JRCManagerHost"
    return out


def save_remote_pc_settings(updates: Dict[str, str], set_app_setting) -> Dict[str, str]:
    clean = {k: (v or "").strip() for k, v in updates.items() if k in SETTING_KEYS}
    for k, v in clean.items():
        set_app_setting(k, v)
    return clean


def tailscale_status() -> Dict[str, Any]:
    exe = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    if not Path(exe).exists():
        return {"installed": False, "online": False, "self_ip": "", "dns_name": "", "error": "not_installed"}
    try:
        proc = subprocess.run(
            [exe, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode != 0:
            return {"installed": True, "online": False, "error": (proc.stderr or proc.stdout or "status failed")[:200]}
        data = json.loads(proc.stdout or "{}")
        self_obj = data.get("Self") or {}
        ips = self_obj.get("TailscaleIPs") or []
        return {
            "installed": True,
            "online": bool(self_obj.get("Online")),
            "self_ip": ips[0] if ips else "",
            "dns_name": self_obj.get("DNSName") or "",
            "hostname": self_obj.get("HostName") or "",
            "raw_backend": data.get("BackendState") or "",
        }
    except Exception as exc:
        return {"installed": True, "online": False, "error": str(exc)[:200]}


def probe_tcp(host: str, port: int, timeout: float = 1.5) -> bool:
    host = (host or "").strip()
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_host_ports(host: str) -> Dict[str, Any]:
    host = (host or "").strip()
    ports = {
        "3389": "RDP",
        "445": "SMB",
        "5985": "WinRM",
        "8765": "JRC_Manager",
        "21116": "RustDesk",
    }
    results: Dict[str, Any] = {"host": host, "ports": {}}
    for port, label in ports.items():
        p = int(port)
        open_ok = probe_tcp(host, p)
        results["ports"][port] = {"label": label, "open": open_ok}
    results["any_open"] = any(v["open"] for v in results["ports"].values())
    return results


def probe_jrc_health(base_url: str, timeout: float = 2.0) -> Tuple[bool, Dict[str, Any]]:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return False, {"error": "no_url"}
    if not url.startswith("http"):
        url = "http://" + url
    health = url + "/api/health"
    try:
        with urllib.request.urlopen(health, timeout=timeout) as resp:
            body = resp.read(8192).decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip().startswith("{") else {}
            ok = resp.status == 200
            return ok, data if isinstance(data, dict) else {"status_code": resp.status}
    except urllib.error.HTTPError as exc:
        return False, {"http_status": exc.code}
    except Exception as exc:
        return False, {"error": str(exc)}


def build_remote_pc_status(get_app_setting) -> Dict[str, Any]:
    settings = get_remote_pc_settings(get_app_setting)
    lan_ip = settings.get("remote_host_lan_ip") or _default_host_lan_ip()
    ts_ip = settings.get("remote_host_tailscale_ip") or ""
    ts = tailscale_status()
    if not ts_ip and ts.get("self_ip"):
        ts_ip = ts.get("self_ip", "")

    lan_probe = probe_host_ports(lan_ip)
    ts_probe = probe_host_ports(ts_ip) if ts_ip else {"host": "", "ports": {}, "any_open": False}

    jrc_lan_ok, jrc_lan_data = probe_jrc_health(f"http://{lan_ip}:8765")
    jrc_ts_ok, jrc_ts_data = (
        probe_jrc_health(f"http://{ts_ip}:8765") if ts_ip else (False, {"error": "no_tailscale_ip"})
    )

    rd_paths = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "RustDesk" / "rustdesk.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "RustDesk" / "rustdesk.exe",
    ]
    rustdesk_installed = any(p.exists() for p in rd_paths)

    return {
        "settings": settings,
        "tailscale": ts,
        "lan_probe": lan_probe,
        "tailscale_probe": ts_probe,
        "jrc_lan": {"ok": jrc_lan_ok, "data": jrc_lan_data},
        "jrc_tailscale": {"ok": jrc_ts_ok, "data": jrc_ts_data},
        "rustdesk_office_installed": rustdesk_installed,
        "internet_ready": bool(ts.get("online")) and (ts_probe.get("any_open") or jrc_ts_ok),
        "recommended": {
            "full_pc_internet": "Tailscale + RustDesk (or RDP to Tailscale IP)",
            "app_internet": f"http://{ts_ip or 'TAILSCALE_IP'}:8765/login",
            "lan_full_pc": f"mstsc /v:{lan_ip}",
            "lan_app": f"http://{lan_ip}:8765/login",
        },
    }


def office_connect_script_path() -> Optional[Path]:
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / "projects" / "HOST-PC-ADMIN" / "tools" / "Connect-ToHostFromOffice.ps1",
        Path(os.environ.get("USERPROFILE", "")) / "projects" / "JRC-Construction-Office" / "tools" / "Connect-ToHostFromOffice.ps1",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "Connect-ToHostFromOffice.ps1",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def launch_office_connect(host_ip: str = "") -> Tuple[bool, str]:
    script = office_connect_script_path()
    if not script:
        return False, "Connect-ToHostFromOffice.ps1 not found on this PC"
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    if host_ip:
        args.extend(["-HostIP", host_ip])
    try:
        subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        return True, f"Launched {script.name}"
    except Exception as exc:
        return False, str(exc)


def wake_on_lan_script_path() -> Optional[Path]:
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / "projects" / "HOST-PC-ADMIN" / "tools" / "Send-WakeOnLan-ToHost.ps1",
        Path(os.environ.get("USERPROFILE", "")) / "projects" / "JRC-Construction-Office" / "tools" / "Send-WakeOnLan-ToHost.ps1",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def is_office_server_pc() -> bool:
    name = (os.environ.get("COMPUTERNAME") or "").upper()
    return name in ("JRCONST", "JRCONST") or os.environ.get("JRC_OFFICE_SERVER") == "1"


def launch_rustdesk() -> Tuple[bool, str]:
    for p in [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "RustDesk" / "rustdesk.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "RustDesk" / "rustdesk.exe",
    ]:
        if p.exists():
            try:
                subprocess.Popen([str(p)], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
                return True, f"Started RustDesk: {p}"
            except Exception as exc:
                return False, str(exc)
    return False, "RustDesk not installed on this PC"


def launch_rdp(host_ip: str) -> Tuple[bool, str]:
    host_ip = (host_ip or _default_host_lan_ip()).strip()
    mstsc = shutil.which("mstsc") or r"C:\Windows\System32\mstsc.exe"
    if not Path(mstsc).exists():
        return False, "mstsc.exe not found"
    try:
        subprocess.Popen([mstsc, f"/v:{host_ip}"])
        return True, f"Opened Remote Desktop to {host_ip}"
    except Exception as exc:
        return False, str(exc)


def read_host_mac() -> str:
    mac_file = Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "JRC_HOST_MAC_ADDRESS.txt"
    if mac_file.exists():
        try:
            line = mac_file.read_text(encoding="utf-8").strip().splitlines()[0]
            if line:
                return line.strip()
        except Exception:
            pass
    return "AC-FD-CE-69-9D-4E"


def run_backdoor_verification(get_app_setting=None) -> Dict[str, Any]:
    """Verify backdoor scripts and host reachability (admin UI checklist)."""
    checks: List[Dict[str, Any]] = []
    home = Path(os.environ.get("USERPROFILE", ""))

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    script_names = [
        "Connect-ToHostFromOffice.ps1",
        "Send-WakeOnLan-ToHost.ps1",
        "ENABLE_HOST_POWER_RECOVERY.ps1",
        "ENABLE_HOST_REMOTE_ACCESS.ps1",
        "ENABLE_INTERNET_REMOTE_ACCESS.ps1",
        "FINISH_HOST_COMPLETE.ps1",
    ]
    for base in [
        home / "projects" / "HOST-PC-ADMIN" / "tools",
        home / "projects" / "JRC-Construction-Office" / "tools",
    ]:
        if base.exists():
            for sn in script_names:
                add(f"Script {sn}", (base / sn).exists(), str(base))
            break

    add("remote_pc_control module", (BASE_DIR / "app" / "remote_pc_control.py").exists())
    add("remote_pc_routes module", (BASE_DIR / "app" / "remote_pc_routes.py").exists())
    add("Office server PC", is_office_server_pc(), os.environ.get("COMPUTERNAME", ""))

    rd = any(
        p.exists()
        for p in [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "RustDesk" / "rustdesk.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "RustDesk" / "rustdesk.exe",
        ]
    )
    add("RustDesk on server PC", rd)

    ts = tailscale_status()
    add("Tailscale installed", ts.get("installed"), ts.get("error", ""))
    add("Tailscale online", ts.get("online"), ts.get("self_ip", ""))

    add("SMB share junction", Path(r"C:\JRC-HOST-SHARE").exists())

    lan = _default_host_lan_ip()
    if get_app_setting:
        lan = get_remote_pc_settings(get_app_setting).get("remote_host_lan_ip") or lan
    probe = probe_host_ports(lan)
    for port, info in probe.get("ports", {}).items():
        add(f"Host {info.get('label', port)} :{port}", info.get("open"), lan)

    jrc_ok, _ = probe_jrc_health(f"http://{lan}:8765")
    add("JRC host health :8765", jrc_ok, f"http://{lan}:8765")

    wol_ok, wol_msg = send_wake_on_lan(read_host_mac(), lan)
    add("Wake-on-LAN send", wol_ok, wol_msg[:120])

    passed = sum(1 for c in checks if c["ok"])
    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "all_ok": passed == len(checks) and len(checks) > 0,
        "verified_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def send_wake_on_lan(mac: str = "", host_ip: str = "") -> Tuple[bool, str]:
    script = wake_on_lan_script_path()
    if not script:
        return False, "Send-WakeOnLan-ToHost.ps1 not found on office PC"
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    if mac:
        args.extend(["-MacAddress", mac])
    if host_ip:
        args.extend(["-HostIP", host_ip])
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0
        return ok, out.strip() or ("Wake packet sent" if ok else "WOL failed")
    except Exception as exc:
        return False, str(exc)


def office_host_command_script() -> Optional[Path]:
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / "projects" / "JRC-Construction-Office" / "tools" / "Invoke-HostOfficeCommand.ps1",
        Path(os.environ.get("USERPROFILE", "")) / "projects" / "HOST-PC-ADMIN" / "tools" / "Invoke-HostOfficeCommand.ps1",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def run_office_host_command(command: str) -> Tuple[bool, str]:
    script = office_host_command_script()
    if not script:
        return False, "Invoke-HostOfficeCommand.ps1 not found"
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode == 0, out or f"Queued {command}"
    except Exception as exc:
        return False, str(exc)


def run_host_power_api(host_ip: str, action: str, delay_seconds: int = 45) -> Tuple[bool, str]:
    """Call host JRC shutdown/reboot API via office Python helper."""
    host_ip = (host_ip or "").strip()
    if not host_ip:
        return False, "No host IP configured"
    tool = Path(os.environ.get("USERPROFILE", "")) / "projects" / "JRC-Construction-Office" / "tools"
    script = "remote_host_shutdown.py" if action == "shutdown" else "remote_host_reboot_verify.py"
    py_path = tool / script
    if not py_path.exists():
        return False, f"{script} not found"
    args = [sys.executable, str(py_path), host_ip]
    if action == "shutdown":
        args.append(str(delay_seconds))
    else:
        args.extend(["reboot", str(max(30, delay_seconds))])
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=90, env=os.environ.copy())
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        ok = proc.returncode == 0 or ('"ok": true' in out or '"ok":true' in out)
        if not ok:
            ok, qmsg = run_office_host_command(action)
            if ok:
                return True, f"API failed; queued via share. {qmsg[:200]}"
        return ok, out[:500] or f"Host {action} requested"
    except Exception as exc:
        return False, str(exc)
