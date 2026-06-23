"""Runtime helpers shared by desktop and launcher scripts."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
LOCAL_HOST_SETTINGS_PATH = BASE_DIR / "data" / "local_host_settings.json"
DEFAULT_PORT = int(os.environ.get("JRC_PORT", "8765"))
FALLBACK_PORT_COUNT = 15
JRC_APP_MARKERS = ("J and R Construction Manager", "J & R Construction", "JRC")
LAN_FIREWALL_RULE_NAME = "J and R Construction Manager Shared Host LAN"


def lan_firewall_port_range() -> tuple[int, int]:
    """TCP port range used by the shared host (includes automatic fallback ports)."""
    start = DEFAULT_PORT
    return start, start + FALLBACK_PORT_COUNT - 1


def lan_firewall_rule_exists() -> bool:
    if os.name != "nt":
        return True
    low, high = lan_firewall_port_range()
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={LAN_FIREWALL_RULE_NAME}"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = (result.stdout or "") + (result.stderr or "")
        if "No rules match" in text:
            return False
        return f"{low}" in text or f"{low}-{high}" in text or "LocalPort:" in text
    except Exception:
        return False


def ensure_lan_firewall() -> tuple[bool, str]:
    """Add inbound Windows Firewall rule for the shared host port range."""
    if os.name != "nt":
        return True, "Firewall helper is only needed on Windows."
    low, high = lan_firewall_port_range()
    port_range = f"{low}-{high}"
    if lan_firewall_rule_exists():
        return True, f"Firewall rule already allows TCP {port_range} on private networks."
    try:
        result = subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f"name={LAN_FIREWALL_RULE_NAME}",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                f"localport={port_range}",
                "profile=private",
                "enable=yes",
            ],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            return True, f"Added firewall rule for TCP {port_range} on private networks."
        err = (result.stderr or result.stdout or "Unknown error").strip()
        return False, f"Could not add firewall rule: {err}"
    except Exception as exc:
        return False, f"Could not add firewall rule: {exc}"


def ensure_lan_firewall_auto(timeout: float = 90.0) -> tuple[bool, str]:
    """Ensure LAN firewall rule exists; auto-prompt for admin on the host PC if needed.

    Phones and other users never need to run anything — only the computer hosting the server.
    """
    if os.name != "nt":
        return True, "Not required on this platform."
    ok, msg = ensure_lan_firewall()
    if ok:
        return True, msg
    if "elevation" not in msg.lower() and "administrator" not in msg.lower():
        return False, msg

    py = python_cmd()
    ps_cmd = (
        f'Start-Process -FilePath "{py}" -ArgumentList "-m","app.allow_lan_firewall" '
        f'-WorkingDirectory "{BASE_DIR}" -Verb RunAs -Wait -WindowStyle Hidden'
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            cwd=str(BASE_DIR),
            timeout=max(15.0, timeout),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return False, "Windows approval timed out. Click Yes on the UAC prompt when starting the host."
    except Exception as exc:
        return False, f"Could not request Windows approval: {exc}"

    deadline = time.time() + timeout
    while time.time() < deadline:
        if lan_firewall_rule_exists():
            low, high = lan_firewall_port_range()
            return True, f"Phone access enabled for TCP {low}-{high} on this host PC."
        time.sleep(0.5)

    return False, "Phone access was not enabled. Click Yes on the one-time Windows security prompt when it appears."


def get_saved_port() -> int:
    try:
        if LOCAL_HOST_SETTINGS_PATH.exists():
            data = json.loads(LOCAL_HOST_SETTINGS_PATH.read_text(encoding="utf-8"))
            return int(data.get("port", DEFAULT_PORT))
    except Exception:
        pass
    return DEFAULT_PORT


def save_port(port: int, note: str = "") -> None:
    LOCAL_HOST_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "port": int(port),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": note or "Port saved by JRC runtime.",
    }
    try:
        LOCAL_HOST_SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass
    os.environ["JRC_PORT"] = str(int(port))


def local_url(path: str = "/login", port: int | None = None) -> str:
    port = int(port or get_saved_port())
    if not path.startswith("/"):
        path = "/" + path
    return f"http://127.0.0.1:{port}{path}"


def is_port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def _fetch(url: str, timeout: float = 0.8) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return int(resp.status), resp.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(4096).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return int(exc.code), body
    except Exception:
        return 0, ""


def is_jrc_server(port: int, timeout: float = 0.8) -> bool:
    """True when this port is serving our Flask app (not some other process)."""
    code, body = _fetch(f"http://127.0.0.1:{port}/api/health", timeout=timeout)
    if code == 200 and any(marker in body for marker in JRC_APP_MARKERS):
        return True
    code, body = _fetch(f"http://127.0.0.1:{port}/login", timeout=timeout)
    if code == 200 and ("Sign in" in body or "Construction Manager" in body):
        return True
    return False


def find_launch_port(start_port: int | None = None, attempts: int = FALLBACK_PORT_COUNT) -> int:
    """Pick a port: reuse JRC if already running, else first free slot from start_port."""
    start = int(start_port if start_port is not None else get_saved_port())
    for port in range(start, start + int(attempts)):
        if is_jrc_server(port):
            return port
        if not is_port_listening(port):
            return port
    return start


def python_cmd() -> str:
    venv = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if venv.exists():
        return str(venv)
    return sys.executable


def _spawn_server(port: int, log_path: Path) -> None:
    try:
        from app.process_lifecycle import prepare_for_new_host, track_popen
        prepare_for_new_host()
    except Exception:
        track_popen = None
        prepare_for_new_host = None
    py = python_cmd()
    env = os.environ.copy()
    env["JRC_PORT"] = str(port)
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"\n--- launch {time.strftime('%Y-%m-%d %H:%M:%S')} port={port} ---\n")
        startupinfo = None
        flags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [py, "-m", "app.network_server"],
            cwd=str(BASE_DIR),
            stdout=logf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            startupinfo=startupinfo,
            creationflags=flags,
        )
        if track_popen:
            track_popen(proc, "network_server", note=f"runtime port {port}")


def ensure_server_running(port: int | None = None, timeout: float = 25.0) -> tuple[bool, int, str]:
    preferred = int(port or get_saved_port())
    port = find_launch_port(preferred)
    login_url = local_url("/login", port)

    if is_jrc_server(port):
        save_port(port, "Reusing running JRC server.")
        return True, port, login_url

    if is_port_listening(port) and not is_jrc_server(port):
        port = find_launch_port(preferred + 1)
        login_url = local_url("/login", port)

    save_port(port, f"Using port {port} (fallback from {preferred} if needed).")
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "web_dashboard_launch.log"
    _spawn_server(port, log_path)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_jrc_server(port):
            return True, port, login_url
        time.sleep(0.75)

    return False, port, login_url


def open_web_dashboard(path: str = "/login") -> tuple[bool, str]:
    ok, port, login_url = ensure_server_running()
    if not path.startswith("/"):
        path = "/" + path
    url = local_url(path, port)
    webbrowser.open(url)
    if ok:
        return True, f"Opened {url}"
    if port != DEFAULT_PORT:
        return True, f"Port {port} in use (preferred port was busy). Opened {url}"
    return False, f"Server still starting on port {port}. Opened {url} — wait a few seconds and refresh."


def cli_open_web() -> int:
    ok, msg = open_web_dashboard("/login")
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(cli_open_web())
