"""
J and R Construction Manager - v7.1 Primary Live Reliable Start Center
Focused repair for menu buttons that appeared to do nothing.

Design goals:
- Keep the Start Center responsive.
- Do not run heavy checks on startup.
- Do not block the UI while tools run.
- Hide command windows where possible, but write logs for every background launch.
- Make normal daily actions clear and simple.
"""
from __future__ import annotations

try:
    from app.win11_compat import enable_win_dpi_awareness
    enable_win_dpi_awareness()
except Exception:
    pass

import os
import json
import socket
import subprocess
import sys
import time
import threading
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog

try:
    from app.dependency_tools import missing_dependencies, status_text, install_optional_dependencies
    from app import ui_theme as theme
    from app.runtime_utils import open_web_dashboard as launch_web_dashboard, find_launch_port, save_port as persist_port, is_jrc_server
except Exception:
    missing_dependencies = lambda: []
    status_text = lambda: "Dependency status unavailable."
    install_optional_dependencies = lambda timeout=300: (False, "Dependency repair unavailable.")
    theme = None
    launch_web_dashboard = None
    find_launch_port = None
    persist_port = None
    is_jrc_server = None

APP_NAME = "J and R Construction Manager"
APP_VERSION = "7.12.1 Densus Owner-Approval Edition"
BUSINESS = "J & R Construction"
OWNER = "Jacob Cosentino"
DEFAULT_PORT = int(os.environ.get("JRC_PORT", "8765"))
BASE_DIR = Path(__file__).resolve().parents[1]
PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PYTHONW = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
PY_CMD = str(PYTHON) if PYTHON.exists() else sys.executable
PYW_CMD = str(PYTHONW) if PYTHONW.exists() else PY_CMD
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)
CLOUD_CONNECT_PATH = BASE_DIR / "data" / "cloud_connect.json"
LOCAL_HOST_SETTINGS_PATH = BASE_DIR / "data" / "local_host_settings.json"
CLOUD_CONNECT_PATH.parent.mkdir(exist_ok=True)


def get_saved_port() -> int:
    try:
        if LOCAL_HOST_SETTINGS_PATH.exists():
            data = json.loads(LOCAL_HOST_SETTINGS_PATH.read_text(encoding="utf-8"))
            return int(data.get("port", DEFAULT_PORT))
    except Exception:
        pass
    return DEFAULT_PORT


def save_saved_port(port: int, note: str = "") -> None:
    try:
        payload = {
            "port": int(port),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": note or "Local host port used by JRC Manager Start Center."
        }
        try:
            from app.host_laptop_roles import load_host_settings, save_host_settings
            merged = load_host_settings(BASE_DIR)
            merged.update(payload)
            save_host_settings(merged, BASE_DIR)
        except Exception:
            LOCAL_HOST_SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


PORT = get_saved_port()

if theme:
    BG, PANEL, CARD, BORDER = theme.BG, theme.PANEL, theme.CARD, theme.BORDER
    TEXT, MUTED, DIM = theme.TEXT, theme.MUTED, theme.DIM
    ACCENT, INFO, WARN, DANGER = theme.ACCENT, theme.INFO, theme.WARN, theme.DANGER
    BUTTON, BUTTON_GREEN = theme.BUTTON, theme.ACCENT
else:
    BG = "#000000"
    PANEL = "#0a0a0a"
    CARD = "#111111"
    BORDER = "#1f2937"
    TEXT = "#f5f5f5"
    MUTED = "#a3a3a3"
    DIM = "#737373"
    ACCENT = "#84cc16"
    INFO = "#a3e635"
    WARN = "#facc15"
    DANGER = "#ef4444"
    BUTTON = "#171717"
    BUTTON_GREEN = "#84cc16"


def stamp() -> str:
    return time.strftime("%Y-%m-%d_%H%M%S")


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None):
            ip = item[4][0]
            if "." in ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def urls() -> dict[str, str]:
    ip = lan_ip()
    local = f"http://127.0.0.1:{PORT}"
    lan = f"http://{ip}:{PORT}"
    return {
        "local": local,
        "lan": lan,
        "health": local + "/api/health",
        "connect": lan + "/connect",
        "mobile": lan + "/mobile",
        "register": lan + "/register",
        "apply": lan + "/apply",
        "remote_mobile": local + "/remote-mobile",
    }


def url_ok(url: str, timeout: float = 0.75) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return True, r.read(250).decode("utf-8", "ignore") or "OK"
    except Exception as exc:
        return False, str(exc)


def is_host_running() -> bool:
    ok, _ = url_ok(urls()["health"], timeout=0.75)
    return ok

def is_login_ready() -> bool:
    ok, _ = url_ok(urls()["local"] + "/login", timeout=0.9)
    return ok

def wait_for_login(timeout: float = 18.0, step: float = 0.75) -> tuple[bool, str]:
    deadline = time.time() + timeout
    last = "Login page did not answer yet."
    while time.time() < deadline:
        ok, msg = url_ok(urls()["local"] + "/login", timeout=1.0)
        if ok:
            return True, "Login page is ready."
        last = msg
        time.sleep(step)
    return False, last

def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def find_available_port(start_port: int = DEFAULT_PORT, attempts: int = 15) -> int:
    if find_launch_port:
        return find_launch_port(start_port, attempts)
    for port in range(int(start_port), int(start_port) + int(attempts)):
        test_url = f"http://127.0.0.1:{port}/api/health"
        ok, _ = url_ok(test_url, timeout=0.45)
        if ok:
            return port
        if not is_port_open(port):
            return port
    return int(start_port)


def set_runtime_port(port: int, note: str = "") -> None:
    global PORT
    PORT = int(port)
    os.environ["JRC_PORT"] = str(PORT)
    if persist_port:
        persist_port(PORT, note)
    else:
        save_saved_port(PORT, note)



def tail_log(path: Path, lines: int = 18) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(data[-lines:])
    except Exception as exc:
        return f"Could not read log: {exc}"


def wait_for_host(timeout: float = 22.0, step: float = 0.8) -> tuple[bool, str, dict[str, tuple[bool, str]]]:
    """Wait for the shared host to respond and test the important lightweight endpoints.

    This avoids the old false failure where the server was still starting when the
    Start Center checked it only once.
    """
    u = urls()
    checks: dict[str, tuple[bool, str]] = {}
    deadline = time.time() + timeout
    last_msg = "Host did not answer yet."
    while time.time() < deadline:
        ok, msg = url_ok(u["health"], timeout=1.0)
        checks["api_health"] = (ok, msg)
        if ok:
            ping_ok, ping_msg = url_ok(u["local"] + "/mobile/ping", timeout=1.0)
            conn_ok, conn_msg = url_ok(u["local"] + "/api/connection", timeout=1.0)
            checks["mobile_ping"] = (ping_ok, ping_msg)
            checks["api_connection"] = (conn_ok, conn_msg)
            if ping_ok and conn_ok:
                return True, "Shared host verified. Health, mobile ping, and connection API all answered.", checks
            last_msg = f"Server answered health but not all endpoints yet. Ping={ping_ok}, Connection={conn_ok}"
        else:
            last_msg = msg
        time.sleep(step)
    return False, last_msg, checks


def quick_test_summary(checks: dict[str, tuple[bool, str]]) -> str:
    if not checks:
        return "No endpoint checks completed."
    labels = {
        "api_health": "API Health",
        "mobile_ping": "Mobile Ping",
        "api_connection": "Connection API",
    }
    out = []
    for key in ["api_health", "mobile_ping", "api_connection"]:
        if key in checks:
            ok, msg = checks[key]
            out.append(f"{labels.get(key, key)}: {'OK' if ok else 'FAILED'} - {str(msg)[:180]}")
    return "\n".join(out)


def _startupinfo() -> tuple[object | None, int]:
    if os.name != "nt":
        return None, 0
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return startupinfo, flags


def write_log_header(path: Path, title: str) -> None:
    with open(path, "a", encoding="utf-8", errors="replace") as f:
        f.write("\n" + "=" * 70 + "\n")
        f.write(f"{title}\n")
        f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Program folder: {BASE_DIR}\n")
        f.write("=" * 70 + "\n")


def launch_hidden(args: list[str], log_name: str, env: dict[str, str] | None = None) -> tuple[subprocess.Popen | None, Path, str]:
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / log_name
    write_log_header(log_path, " ".join(args))
    startupinfo, flags = _startupinfo()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        log = open(log_path, "a", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(
            args,
            cwd=str(BASE_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=flags,
            env=merged_env,
        )
        if any("network_server" in str(a) for a in args):
            try:
                from app.host_process import write_host_pid
                write_host_pid(proc.pid)
            except Exception:
                pass
        return proc, log_path, ""
    except Exception as exc:
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"LAUNCH ERROR: {exc}\n")
        return None, log_path, str(exc)


def open_path(path: Path) -> None:
    try:
        path.mkdir(exist_ok=True) if path.suffix == "" and not path.exists() else None
        if os.name == "nt":
            os.startfile(str(path))
        else:
            webbrowser.open(str(path))
    except Exception as exc:
        messagebox.showwarning("Could not open", str(exc))


def normalize_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value


def get_cloud_base_url() -> str:
    try:
        data = json.loads(CLOUD_CONNECT_PATH.read_text(encoding="utf-8"))
        return normalize_base_url(data.get("cloud_base_url", ""))
    except Exception:
        return ""


def set_cloud_base_url(value: str) -> str:
    try:
        from app.cloud_url_sync import sync_cloud_url
        return sync_cloud_url(value)
    except Exception:
        value = normalize_base_url(value)
        payload = {
            "cloud_base_url": value,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": "Cloud URL is used by Start Center when local host is not running. Remote users can only connect when this cloud/tunnel/VPN URL points to a running hosted JRC server."
        }
        CLOUD_CONNECT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return value


def link_set(base: str) -> dict[str, str]:
    base = normalize_base_url(base)
    if not base:
        return {}
    return {
        "base": base,
        "connect": base + "/connect",
        "mobile": base + "/mobile",
        "register": base + "/register",
        "apply": base + "/apply",
        "health": base + "/api/health",
        "connection": base + "/api/connection",
    }




class HostMonitor(tk.Toplevel):
    """Small, lightweight server monitor and quick tools panel."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("JRC Host Monitor")
        self.configure(bg=BG)
        self.geometry("540x360")
        self.minsize(500, 320)
        tk.Label(self, text="Local Host Monitor", bg=BG, fg=TEXT, font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=18, pady=(16,4))
        tk.Label(self, text="Use this to see whether the local server is actually answering before sharing phone links.", bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=480, justify="left").pack(anchor="w", padx=18)
        self.status = tk.StringVar(value="Checking...")
        self.links = tk.StringVar(value="")
        card = tk.Frame(self, bg=PANEL, padx=14, pady=12, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=18, pady=14)
        tk.Label(card, textvariable=self.status, bg=PANEL, fg=INFO, font=("Segoe UI", 11, "bold"), justify="left", wraplength=470).pack(anchor="w")
        tk.Label(card, textvariable=self.links, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), justify="left", wraplength=470).pack(anchor="w", pady=(8,12))
        btns = tk.Frame(card, bg=PANEL)
        btns.pack(fill="x", pady=(4,0))
        for label, cmd in [
            ("Refresh", self.refresh),
            ("Open Connect", lambda: webbrowser.open(urls()["connect"])),
            ("Mobile", lambda: webbrowser.open(urls()["mobile"])),
            ("Auto Repair", self.parent.auto_host_repair),
            ("Logs", lambda: open_path(LOG_DIR)),
        ]:
            tk.Button(btns, text=label, command=cmd, bg=BUTTON, fg=TEXT, relief="flat", padx=8, pady=7).pack(side="left", padx=3)
        self.after(100, self.refresh)
        self.after(5000, self._loop)

    def _loop(self):
        try:
            if self.winfo_exists():
                self.refresh()
                self.after(5000, self._loop)
        except Exception:
            pass

    def refresh(self):
        u = urls()
        login_ok, login_msg = url_ok(u["local"] + "/login", timeout=0.8)
        health_ok, health_msg = url_ok(u["health"], timeout=0.8)
        ping_ok, ping_msg = url_ok(u["local"] + "/mobile/ping", timeout=0.8)
        conn_ok, conn_msg = url_ok(u["local"] + "/api/connection", timeout=0.8)
        cloud = get_cloud_base_url()
        if login_ok and health_ok and ping_ok and conn_ok:
            state = "RUNNING AND VERIFIED"
            fg_msg = f"Status: {state}\nPort: {PORT}\nLAN IP: {lan_ip()}\nLogin: OK | Health: OK | Mobile Ping: OK | Connection API: OK"
        elif login_ok:
            state = "LOGIN READY - MOBILE NEEDS ATTENTION"
            fg_msg = f"Status: {state}\nPort: {PORT}\nLAN IP: {lan_ip()}\nLogin: OK | Health: {health_ok} | Mobile Ping: {ping_ok} | Connection API: {conn_ok}\nYou can log in locally. Run Auto Repair Host if mobile/phone links fail."
        elif is_port_open(PORT):
            state = "PORT OPEN BUT LOGIN NOT VERIFIED"
            fg_msg = f"Status: {state}\nPort: {PORT}\nLogin: {login_ok} | Health: {health_ok} | Mobile Ping: {ping_ok} | Connection API: {conn_ok}\nRun Auto Repair Host if this continues."
        else:
            state = "NOT RUNNING"
            fg_msg = f"Status: {state}\nPort: {PORT}\nClick Start Local Host, or use Cloud Access for remote users."
        self.status.set(fg_msg)
        self.links.set(
            f"Connection Test: {u['connect']}\nMobile: {u['mobile']}\nCloud URL: {cloud or 'not set'}"
        )

class MobileWindow(tk.Toplevel):
    def __init__(self, parent, base_url: str | None = None, mode: str = "local"):
        super().__init__(parent)
        self.title("Mobile and Shared Access")
        self.configure(bg=BG)
        self.geometry("800x570")
        self.minsize(680, 500)
        if base_url:
            links = link_set(base_url)
        else:
            links = urls()
        mode_label = "Cloud / Remote Access" if mode == "cloud" else "Local Same-Wi-Fi / VPN Access"
        tk.Label(self, text="Mobile and Shared Access", bg=BG, fg=TEXT, font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=22, pady=(18, 6))
        tk.Label(self, text=f"Mode: {mode_label}", bg=BG, fg=INFO if mode == "cloud" else WARN, font=("Segoe UI", 11, "bold"), wraplength=730, justify="left").pack(anchor="w", padx=22)
        help_text = (
            "Cloud mode does not depend on this PC host. Other users can connect while this computer is off only if the cloud/tunnel/VPN server is running."
            if mode == "cloud" else
            "Local mode requires this PC host to be running and is best for same-Wi-Fi or VPN testing. For other locations, use Cloud mode."
        )
        tk.Label(self, text=help_text, bg=BG, fg=MUTED, font=("Segoe UI", 10), wraplength=730, justify="left").pack(anchor="w", padx=22, pady=(4,0))
        box = tk.Frame(self, bg=PANEL, padx=16, pady=14)
        box.pack(fill="both", expand=True, padx=22, pady=16)
        items = [
            ("Connection Test", links.get("connect", ""), "Use this first to confirm the phone or outside user can reach the program."),
            ("Mobile App", links.get("mobile", ""), "Phone-friendly J&R Manager screen."),
            ("Worker Signup", links.get("register", ""), "User requests an account. Admin must approve."),
            ("Job Application", links.get("apply", ""), "Worker/job application and insurance onboarding form."),
        ]
        for name, link, desc in items:
            row = tk.Frame(box, bg=PANEL)
            row.pack(fill="x", pady=7)
            tk.Label(row, text=name, width=17, anchor="w", bg=PANEL, fg=INFO, font=("Segoe UI", 11, "bold")).pack(side="left")
            entry = tk.Entry(row, bg="#0f172a", fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 9))
            entry.insert(0, link)
            entry.pack(side="left", fill="x", expand=True, padx=(6, 8), ipady=5)
            tk.Button(row, text="Open", bg=BUTTON, fg=TEXT, relief="flat", command=lambda l=link: webbrowser.open(l) if l else None).pack(side="right")
            tk.Label(box, text=desc, bg=PANEL, fg=DIM, font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=(180, 0))
        bottom = "Cloud links stay usable when your PC host is off only when the hosted/cloud server is actually deployed and running." if mode == "cloud" else "If phone fails on same Wi-Fi, run Tools / Repair > Allow Phone Access and restart the local host."
        tk.Label(self, text=bottom, bg=BG, fg=WARN, font=("Segoe UI", 9, "bold"), wraplength=730, justify="left").pack(anchor="w", padx=22, pady=(0, 14))


class HelpWindow(tk.Toplevel):
    def __init__(self, parent, title: str, body: str):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.geometry("680x440")
        tk.Label(self, text=title, bg=BG, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=22, pady=(18, 8))
        txt = tk.Text(self, wrap="word", bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", padx=14, pady=14, font=("Segoe UI", 10))
        txt.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        txt.insert("1.0", body)
        txt.configure(state="disabled")


def read_local_sessions() -> list[dict]:
    db_path = BASE_DIR / "data" / "jr_business.db"
    if not db_path.exists():
        return []
    try:
        import sqlite3
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 15 * 60))
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT session_id, username, role, ip_address, login_time, last_seen FROM online_sessions WHERE active=1 AND revoked=0 AND last_seen >= ? ORDER BY last_seen DESC",
                (cutoff,),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


def revoke_local_session(session_id: str) -> bool:
    db_path = BASE_DIR / "data" / "jr_business.db"
    try:
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE online_sessions SET revoked=1, active=0, revoke_reason=? WHERE session_id=?",
                ("Revoked from Start Center admin monitor", session_id),
            )
            conn.commit()
        return True
    except Exception:
        return False


class AdminServerPanel(tk.Frame):
    """Docked admin strip at top of Start Center — does not cover action cards."""

    def __init__(self, parent: tk.Misc, start_center: "StartCenter"):
        super().__init__(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        self.parent = start_center
        self.expanded = False
        self._sessions: list[dict] = []
        self._wrap = 520
        self.status_var = tk.StringVar(value="Server: checking...")

        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(head, text="Admin Panel", bg=PANEL, fg=ACCENT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.toggle_btn = tk.Button(
            head, text="+", relief="flat", bg=PANEL, fg=MUTED, command=self.toggle, padx=8, cursor="hand2"
        )
        self.toggle_btn.pack(side="right")
        self.status_lbl = tk.Label(
            head,
            textvariable=self.status_var,
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 9),
            wraplength=self._wrap,
            justify="left",
            anchor="w",
        )
        self.status_lbl.pack(side="left", fill="x", expand=True, padx=(10, 8))

        quick = tk.Frame(head, bg=PANEL)
        quick.pack(side="right", padx=(0, 4))
        for label, cmd in (
            ("Start", self.parent.start_host),
            ("Stop", self.parent.stop_host),
            ("Admin", self.open_admin_web),
            ("Accounts", self.open_admin_accounts),
        ):
            tk.Button(
                quick,
                text=label,
                command=cmd,
                bg=BUTTON,
                fg=TEXT,
                relief="flat",
                padx=8,
                pady=3,
                font=("Segoe UI", 8, "bold"),
                cursor="hand2",
            ).pack(side="left", padx=2)

        self.body = tk.Frame(self, bg=PANEL)
        self.session_box = tk.Listbox(
            self.body,
            height=3,
            bg="#0f172a",
            fg=TEXT,
            selectbackground=BUTTON,
            font=("Segoe UI", 8),
            relief="flat",
            highlightthickness=0,
        )
        self.session_box.pack(fill="x", padx=10, pady=(0, 6))
        btns = tk.Frame(self.body, bg=PANEL)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        for label, cmd in (
            ("Mobile Links", self.parent.mobile_links),
            ("Account DB", self.open_admin_accounts),
            ("Host Monitor", self.parent.show_host_monitor),
            ("Admin Web", self.open_admin_web),
            ("End Session", self.revoke_selected),
        ):
            tk.Button(
                btns,
                text=label,
                command=cmd,
                bg=BUTTON,
                fg=TEXT,
                relief="flat",
                padx=8,
                pady=4,
                font=("Segoe UI", 8),
                cursor="hand2",
            ).pack(side="left", padx=2, pady=2)

        self.after(900, self.refresh)
        self.after(5000, self._loop)

    def set_wraplength(self, width: int) -> None:
        self._wrap = max(180, width)
        self.status_lbl.configure(wraplength=self._wrap)

    def toggle(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.body.pack(fill="x")
            self.toggle_btn.configure(text="−")
        else:
            self.body.pack_forget()
            self.toggle_btn.configure(text="+")

    def _loop(self):
        try:
            if self.winfo_exists():
                self.refresh()
                self.after(5000, self._loop)
        except Exception:
            pass

    def refresh(self):
        running = is_host_running()
        cloud = get_cloud_base_url()
        sessions: list[dict] = []
        if running:
            try:
                with urllib.request.urlopen(urls()["local"] + "/api/local-host-admin", timeout=1.0) as resp:
                    data = json.loads(resp.read().decode("utf-8", "ignore"))
                    sessions = data.get("sessions") or []
            except Exception:
                sessions = read_local_sessions()
        else:
            sessions = read_local_sessions()
        self._sessions = sessions
        mode = "CLOUD" if cloud and not running else ("RUNNING" if running else "STOPPED")
        self.status_var.set(
            f"Server: {mode} | Port {PORT} | Active users: {len(sessions)}\n"
            f"LAN: {lan_ip()} | Cloud: {cloud or 'not set'}"
        )
        self.session_box.delete(0, "end")
        for s in sessions[:12]:
            self.session_box.insert("end", f"{s.get('username','?')} ({s.get('role','')}) — {s.get('ip_address','')}")

    def open_admin_web(self):
        if is_host_running():
            webbrowser.open(urls()["local"] + "/admin")
        else:
            messagebox.showinfo("Start Host First", "Start the local host, then open the web admin panel.")

    def open_admin_accounts(self):
        self.parent.open_admin_accounts()

    def revoke_selected(self):
        sel = self.session_box.curselection()
        if not sel:
            messagebox.showinfo("Select Session", "Select a user session, then click End Session.")
            return
        idx = sel[0]
        if idx >= len(self._sessions):
            return
        sid = self._sessions[idx].get("session_id", "")
        if not sid:
            return
        if not messagebox.askyesno("End Session", f"End session for {self._sessions[idx].get('username', 'user')}?"):
            return
        if is_host_running():
            try:
                req = urllib.request.Request(urls()["local"] + f"/api/admin/revoke/{sid}", method="POST")
                urllib.request.urlopen(req, timeout=2.0)
            except Exception:
                revoke_local_session(sid)
        else:
            revoke_local_session(sid)
        self.refresh()
        self.parent.set_status("Session ended by admin.")


class StartCenter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1080x780")
        self.minsize(640, 480)
        try:
            self.state("zoomed")
        except Exception:
            pass
        self.configure(bg=BG)
        self.status_var = tk.StringVar(value="Ready — choose a section on the left, then Open an action.")
        self.host_monitor_window = None
        self._nav_buttons: dict[str, tk.Button] = {}
        self._section = "daily"
        self._content_wrap = 560
        if theme:
            theme.apply_window_icon(self, BASE_DIR / "assets" / "j_and_r_manager_icon.ico")
        else:
            try:
                ico = BASE_DIR / "assets" / "j_and_r_manager_icon.ico"
                if ico.exists():
                    self.iconbitmap(str(ico))
            except Exception:
                pass
        self._sections = self._define_sections()
        if not self._admin_developer_pc():
            self._sections = {k: v for k, v in self._sections.items() if k != "developer"}
        self._build()
        self._show_section("daily")
        self.bind("<Configure>", self._on_resize)
        self._wheel_bound = False
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)
        try:
            from app.data_pipeline import ensure_master_storage_layout, run_master_pipeline_maintenance
            threading.Thread(target=lambda: run_master_pipeline_maintenance(BASE_DIR / "data" / "jr_business.db"), daemon=True, name="jrc-pipeline").start()
            ensure_master_storage_layout()
        except Exception:
            pass
        self.after(700, self._run_startup_setup_if_needed)
        self.after(1200, self._show_dedicated_host_welcome)

    def _define_sections(self):
        return {
            "daily": ("Home", [
                ("Open Dashboard", "Your role-based home — all features in one place.", self.open_dashboard, "primary"),
                ("Open Office", "Desktop jobs, invoices, payroll, files.", self.open_office, "info"),
                ("Web Dashboard", "Browser UI — same login, unified dashboard.", self.open_web_dashboard, "info"),
            ]),
            "hosting": ("Hosting & mobile", [
                ("Start Host Server (Easy)", "Dedicated laptop: one window — keep open for 24/7 LAN host.", self.start_dedicated_host_easy, "primary"),
                ("Start Local Host", "Run the web server on THIS laptop (office or dedicated host).", self.start_host, "info"),
                ("Stop Local Host", "Safely stop the server — data is checkpointed and backed up.", self.stop_host, "warn"),
                ("Connect to Remote Host", "Open browser to the other laptop's host (when it is running 24/7).", self.connect_remote_host, "primary"),
                ("Host Laptop Setup", "Mark this PC as Office or Dedicated 24/7 host + set remote URL.", self.host_laptop_setup_wizard, "info"),
                ("Host Monitor", "Live status for login readiness, health checks, and shareable links.", self.show_host_monitor, "secondary"),
                ("Mobile Links", "Connection test, mobile app, worker signup, and job application URLs.", self.mobile_links, "secondary"),
                ("Cloud Access", "Remote URL when this PC is off — Render, Railway, Fly.io, or tunnel.", self.cloud_options, "info"),
            ]),
            "setup": ("Setup & verify", [
                ("Install / Update", "Full owner or worker install wizard — use after download or on a new PC.", self.run_install_or_update, "primary"),
                ("First Setup / Login", "Secure local login + post-install wizard (same as after install).", self.first_setup_login, "info"),
                ("Background Troubleshooter", "Automated system check, host repair, payments schema, shortcuts — full report.", self.run_background_troubleshooter, "warn"),
                ("Self Setup + Verify", "Post-login checks; writes a report to exports and logs.", self.self_setup_verify, "warn"),
                ("Primary Live Server", "24/7 cloud deployment checklist and readiness tools.", self.primary_live_server, "primary"),
                ("Auto Repair Host", "Fix dependencies, ports, and common host issues automatically.", self.auto_host_repair, "warn"),
            ]),
            "admin": ("Admin & security", [
                ("Admin Web Panel", "Users, sessions, devices — requires host running.", self.open_admin_web_panel, "primary"),
                ("Densus Security Hub", "Owner-approved admin monitor + download.", self.open_densus_hub, "primary"),
                ("Account Database Editor", "Users, roles, permission overrides.", self.open_admin_accounts, "primary"),
                ("All Database Tables", "Browse/edit SQLite tables.", self.open_admin_database, "info"),
                ("Owner Security Status", "Default password and owner setup.", self.pre_install_security_check, "warn"),
            ]),
            "tools": ("Tools & files", [
                ("Print File to A42", "Print a PDF or text file to the Phoswift label printer (USB).", self.print_local_file, "primary"),
                ("Open Business Workspace", "One Dropbox folder — quotes, logs, office CSVs (phone + desktop).", self.open_business_workspace, "primary"),
                ("Sync Business Workspace", "Unify Dropbox paths, deploy 00_START_HERE, refresh readable reports.", self.run_sync_business_workspace, "primary"),
                ("Worker Forms", "Account signup, customer request, and job application links.", self.worker_forms, "secondary"),
                ("Tools / Repair", "System check, host test, firewall rule, and final verify.", self.tools_window, "warn"),
                ("Files / Logs", "Exports, backups, logs, program folder, and help documents.", self.files_window, "secondary"),
            ]),
            "developer": ("Developer & admin", [
                ("Full Live Update", "Sync files, verify packages, run all checks, log and save LIVE_UPDATE_REPORT.txt.", self.run_live_full_update, "primary"),
                ("Office Records Sync", "Import job register + payroll from the same unified workspace.", self.run_office_records_sync, "primary"),
                ("Phase Verification", "Run all phase checks; saves PHASE_VERIFICATION_REPORT.txt.", self.run_phase_verification, "info"),
                ("Developer Tools Console", "Every QA, repair, and admin script — full bells and whistles.", self.developer_tools_window, "info"),
                ("Account Database Editor", "Users, roles, passwords, sessions — /admin/database/accounts.", self.open_admin_accounts, "primary"),
                ("All Database Tables", "Browse/edit any business table in SQLite (/admin/database).", self.open_admin_database, "info"),
                ("Developer Status Report", "File manifest, packages, installer source paths.", self.run_developer_status, "secondary"),
                ("Run Verify Bundle", "Sync test, emergency, permissions, final verify, system + host checks.", self.run_verify_bundle, "warn"),
                ("Initialize Install", "Register trusted admin device and install init log.", self.run_initialize_install, "secondary"),
                ("Seed Emergency Key", "Re-seed owner mastery key (data\\local_secrets.env).", self.seed_emergency_key, "warn"),
                ("Open Installer Source", "Open the package folder recorded at install time.", self.open_installer_source, "secondary"),
            ]),
        }

    def _admin_developer_pc(self) -> bool:
        try:
            from app.admin_developer_suite import is_admin_developer_pc

            return is_admin_developer_pc(BASE_DIR)
        except Exception:
            return True

    def set_status(self, msg: str) -> None:
        self.status_var.set(msg)
        self.update_idletasks()

    def _build(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)

        header = tk.Frame(shell, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x", padx=16, pady=(16, 10))
        accent = tk.Frame(header, bg=ACCENT, height=3)
        accent.pack(fill="x")
        head_inner = tk.Frame(header, bg=PANEL, padx=22, pady=16)
        head_inner.pack(fill="x")
        self._head_title = tk.Label(head_inner, text="J & R Construction Manager", fg=TEXT, bg=PANEL, font=("Segoe UI", 26, "bold"))
        self._head_title.pack(anchor="w")
        self._head_owner = tk.Label(head_inner, text=f"{OWNER}  •  {BUSINESS}", fg=MUTED, bg=PANEL, font=("Segoe UI", 10))
        self._head_owner.pack(anchor="w", pady=(2, 0))
        tk.Label(head_inner, text=f"v{APP_VERSION}", fg=DIM, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")
        try:
            from app.data_pipeline import mode_label as pipeline_mode_label
            from app.host_laptop_roles import host_role_label
            pipeline_txt = pipeline_mode_label() + " | " + host_role_label(BASE_DIR)
        except Exception:
            pipeline_txt = "Data pipeline: standard local"
        self._head_pipeline = tk.Label(
            head_inner, text=pipeline_txt, fg=ACCENT, bg=PANEL, font=("Segoe UI", 9, "bold"), wraplength=900, justify="left"
        )
        self._head_pipeline.pack(anchor="w", pady=(4, 0))
        self._head_sub = tk.Label(
            head_inner,
            text="Start Center — Office, browser dashboard, admin panel (top), and hosting tools.",
            fg=INFO,
            bg=PANEL,
            font=("Segoe UI", 10, "bold"),
            wraplength=900,
            justify="left",
        )
        self._head_sub.pack(anchor="w", pady=(8, 0))

        self._admin_dock = tk.Frame(shell, bg=BG)
        self._admin_dock.pack(fill="x", padx=16, pady=(0, 8))
        self.admin_panel = AdminServerPanel(self._admin_dock, self)
        self.admin_panel.pack(fill="x")

        body = tk.Frame(shell, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        sidebar = tk.Frame(body, bg=PANEL, width=theme.SIDEBAR_W if theme else 170, highlightthickness=1, highlightbackground=BORDER)
        self._sidebar = sidebar
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="MENU", bg=PANEL, fg=DIM, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        for key, (label, _) in self._sections.items():
            if theme:
                btn = theme.nav_button(sidebar, label, lambda k=key: self._show_section(k))
            else:
                btn = tk.Button(sidebar, text=label, command=lambda k=key: self._show_section(k))
                btn.pack(fill="x", padx=10, pady=4)
            self._nav_buttons[key] = btn

        content_shell = tk.Frame(body, bg=BG, highlightthickness=1, highlightbackground=BORDER)
        content_shell.pack(side="left", fill="both", expand=True)

        self._section_title = tk.Label(content_shell, text="", bg=PANEL, fg=TEXT, font=("Segoe UI", 15, "bold"), anchor="w", padx=20, pady=14)
        self._section_title.pack(fill="x")

        scroll_host = tk.Frame(content_shell, bg=BG)
        scroll_host.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(scroll_host, bg=BG, highlightthickness=0, bd=0)
        if theme:
            scroll = theme.dark_scrollbar(scroll_host, command=self._canvas.yview)
        else:
            scroll = tk.Scrollbar(scroll_host, orient="vertical", command=self._canvas.yview, bg=BG, troughcolor=PANEL, width=10)
        self._scroll = scroll
        self._cards_frame = tk.Frame(self._canvas, bg=BG)
        self._cards_frame.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas_window = self._canvas.create_window((0, 0), window=self._cards_frame, anchor="nw")
        self._canvas.configure(yscrollcommand=scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="right", fill="y", pady=8, padx=(0, 6))

        self._canvas.bind("<Configure>", self._sync_canvas_width)

        footer = tk.Frame(shell, bg=PANEL, highlightthickness=1, highlightbackground=BORDER, padx=16, pady=10)
        footer.pack(fill="x", padx=16, pady=(0, 14))
        self._footer_label = tk.Label(
            footer, textvariable=self.status_var, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), wraplength=980, justify="left"
        )
        self._footer_label.pack(anchor="w")

    def _bind_wheel(self, _event=None):
        if not self._wheel_bound:
            self._canvas.bind_all("<MouseWheel>", self._on_wheel)
            self._wheel_bound = True

    def _unbind_wheel(self, _event=None):
        if self._wheel_bound:
            self._canvas.unbind_all("<MouseWheel>")
            self._wheel_bound = False

    def _sync_canvas_width(self, event=None):
        try:
            w = self._canvas.winfo_width()
            if w <= 1 and event is not None and hasattr(event, "width"):
                w = event.width
            if w <= 1:
                w = max(400, self.winfo_width() - 240)
            self._canvas.itemconfigure(self._canvas_window, width=max(280, w - 4))
            self._content_wrap = max(280, w - 120)
        except Exception:
            pass

    def _on_wheel(self, event):
        try:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _show_section(self, key: str):
        self._section = key
        label, items = self._sections[key]
        self._section_title.configure(text=label)
        for child in self._cards_frame.winfo_children():
            child.destroy()
        for title, desc, cmd, tone in items:
            if theme:
                theme.action_card(self._cards_frame, title, desc, cmd, variant=tone, wraplength=self._content_wrap)
            else:
                self._legacy_card(title, desc, cmd, tone)
        for nav_key, btn in self._nav_buttons.items():
            active = nav_key == key
            if theme:
                btn.configure(
                    bg=theme.CARD if active else theme.PANEL,
                    fg=theme.TEXT if active else theme.MUTED,
                    highlightbackground=theme.ACCENT if active else theme.BORDER,
                )
        self.set_status(f"{label} — pick an action and click Open.")

    def _legacy_card(self, title, desc, command, tone="secondary"):
        frame = tk.Frame(self._cards_frame, bg=CARD, padx=14, pady=12)
        frame.pack(fill="x", padx=12, pady=6)
        tk.Label(frame, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(frame, text=desc, bg=CARD, fg=MUTED, wraplength=self._content_wrap).pack(anchor="w", pady=4)
        tk.Button(frame, text="Open", command=command).pack(anchor="e")

    def _on_resize(self, event=None):
        if event and event.widget is not self:
            return
        self._sync_canvas_width()
        w = self.winfo_width()
        h = self.winfo_height()
        wrap = max(220, w - 320)
        self._content_wrap = wrap
        if hasattr(self, "_footer_label"):
            self._footer_label.configure(wraplength=max(200, w - 48))
        if hasattr(self, "admin_panel"):
            self.admin_panel.set_wraplength(max(180, w - 380))
        if hasattr(self, "_head_title"):
            size = 18 if w < 820 else 22 if w < 980 else 26
            self._head_title.configure(font=("Segoe UI", size, "bold"))
        for attr, wl in (("_head_pipeline", w - 80), ("_head_sub", w - 80)):
            lbl = getattr(self, attr, None)
            if lbl:
                lbl.configure(wraplength=max(240, wl))
        if hasattr(self, "_sidebar") and w < 760:
            self._sidebar.configure(width=150)
        elif hasattr(self, "_sidebar"):
            self._sidebar.configure(width=theme.SIDEBAR_W if theme else 170)

    def _watch_process(self, proc, log_path: Path, name: str, success_hint: str = ""):
        def check():
            if proc is None:
                self.set_status(f"{name} could not start. Open logs for details: {log_path}")
                messagebox.showwarning("Could not start", f"{name} could not start.\n\nLog: {log_path}")
                return
            code = proc.poll()
            if code is None:
                self.set_status(success_hint or f"{name} is running in the background. Log: {log_path}")
            elif code == 0:
                self.set_status(f"{name} finished. Log: {log_path}")
            else:
                self.set_status(f"{name} stopped with code {code}. Open logs: {log_path}")
                messagebox.showwarning("Process stopped", f"{name} stopped right away with code {code}.\n\nOpen logs to see why:\n{log_path}")
        self.after(1800, check)



    def extreme_final_verify(self):
        self.set_status("Running Extreme Final Verify in the background...")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.extreme_final_verify"], "extreme_final_verify_last.log")
        if err:
            messagebox.showwarning("Could not start", err)
        self._watch_process(proc, log, "Extreme Final Verify", "Extreme Final Verify is running. Report will be saved in exports.")

    def open_admin_web_panel(self):
        """Start host if needed; admin status stays in the docked top panel (browser opens only for full web UI)."""
        if not self._require_business_storage("open the admin web panel"):
            return
        if is_host_running():
            webbrowser.open(urls()["local"] + "/admin")
            self.set_status("Opened web admin in browser. Server status stays in the Admin Panel strip above.")
            if hasattr(self, "admin_panel"):
                self.admin_panel.refresh()
            return
        if messagebox.askyesno(
            "Start Host for Admin",
            "The admin panel runs in your browser after the local host starts.\n\nStart the host now and open Admin?",
        ):
            self.start_host()

            def wait_admin():
                for _ in range(40):
                    if is_host_running():
                        webbrowser.open(urls()["local"] + "/admin")
                        self.set_status("Admin web panel opened.")
                        if hasattr(self, "admin_panel"):
                            self.admin_panel.refresh()
                        return
                    time.sleep(0.5)
                messagebox.showwarning("Admin Not Ready", "Local host did not verify login. Run Auto Repair Host, then try again.")

            threading.Thread(target=wait_admin, daemon=True).start()

    def open_densus_hub(self):
        """Open Densus JRC Admin Hub — owner approval required for download/use."""
        if not self._require_business_storage("open Densus"):
            return
        target = urls()["local"] + "/admin/densus"
        if is_host_running():
            webbrowser.open(target)
            self.set_status("Opened Densus hub — owner approves each admin before download/use.")
            return
        if messagebox.askyesno(
            "Start Host for Densus",
            "Densus runs in your browser after the local host starts.\n\n"
            "Owner must approve each admin before download or use.\n\nStart host and open Densus?",
        ):
            self.start_host()

            def wait_densus():
                for _ in range(40):
                    if is_host_running():
                        webbrowser.open(target)
                        self.set_status("Densus hub opened.")
                        return
                    time.sleep(0.5)
                messagebox.showwarning("Densus Not Ready", "Host did not start. Run Auto Repair Host, then try again.")

            threading.Thread(target=wait_densus, daemon=True).start()

    def run_install_or_update(self):
        from app.startup_setup import launch_installer

        self.set_status("Opening Install / Update wizard...")
        if launch_installer(BASE_DIR):
            self.set_status("Install / Update wizard opened.")
        else:
            messagebox.showwarning(
                "Installer not found",
                "Could not find INSTALL_J_AND_R_MANAGER.vbs or install_jr_job_manager_ui.ps1 in the program folder.",
            )

    def _run_startup_setup_if_needed(self):
        try:
            from app.startup_setup import evaluate_setup_state, maybe_run_startup_setup

            action, detail = evaluate_setup_state(BASE_DIR)
            if action == "ok":
                return
            self.set_status(f"Setup needed: {detail}")
            action, detail = maybe_run_startup_setup(BASE_DIR)
            if action == "need_installer":
                self.set_status("Install / Update wizard opened automatically (first-time or incomplete setup).")
            elif action == "need_first_run":
                self.set_status("Secure Login and setup wizard opened automatically.")
            elif action != "ok":
                self.set_status(f"Setup: {detail}")
        except Exception as exc:
            self.set_status(f"Setup check skipped: {exc}")

    def _show_dedicated_host_welcome(self):
        try:
            from app.host_laptop_roles import is_dedicated_host_install, load_host_settings
            if not is_dedicated_host_install(BASE_DIR):
                return
            settings = load_host_settings(BASE_DIR)
            if settings.get("dedicated_host_welcome_shown"):
                return
            readme = BASE_DIR / "DEDICATED_HOST_README.txt"
            if not readme.exists():
                if messagebox.askyesno(
                    "Dedicated Host Laptop — First Setup",
                    "This PC is marked as the dedicated 24/7 host.\n\n"
                    "Run ONE-TIME setup now?\n"
                    "(Creates Desktop shortcut + copies office database)\n\n"
                    "YES = Run SETUP_DEDICATED_HOST_LAPTOP.bat\n"
                    "NO = I'll set up later",
                ):
                    bat = BASE_DIR / "SETUP_DEDICATED_HOST_LAPTOP.bat"
                    if bat.exists():
                        subprocess.Popen(["cmd", "/c", str(bat)], cwd=str(BASE_DIR))
                return
            if not settings.get("dedicated_host_setup_complete"):
                return
            lan = settings.get("dedicated_host_lan_url", urls().get("lan", ""))
            messagebox.showinfo(
                "Dedicated Host — Daily Start",
                "This is your 24/7 host laptop.\n\n"
                "EASY START:\n"
                "  Double-click Desktop shortcut:\n"
                "  START JRC Host Server (24-7)\n\n"
                f"LAN URL for office/phones:\n  {lan}\n\n"
                "Local login here: jrc_host\n"
                "Jacob owner login: ivygrows (from office browser)\n\n"
                "See DEDICATED_HOST_README.txt in the program folder.",
            )
            from app.host_laptop_roles import save_host_settings
            save_host_settings({"dedicated_host_welcome_shown": True}, BASE_DIR)
        except Exception:
            pass

    def start_dedicated_host_easy(self):
        """Launch START_DEDICATED_HOST_SERVER.bat — simplest daily host start."""
        bat = BASE_DIR / "START_DEDICATED_HOST_SERVER.bat"
        setup_bat = BASE_DIR / "SETUP_DEDICATED_HOST_LAPTOP.bat"
        if not bat.exists():
            messagebox.showwarning("Missing File", f"Not found:\n{bat}\n\nRun Live Update from office PC first.")
            return
        profile = BASE_DIR / "data" / "install_profile.json"
        if not profile.exists():
            if messagebox.askyesno(
                "First-Time Host Setup",
                "Run one-time dedicated host setup first?\n\nYES = SETUP_DEDICATED_HOST_LAPTOP.bat",
            ) and setup_bat.exists():
                subprocess.Popen(["cmd", "/c", str(setup_bat)], cwd=str(BASE_DIR))
            return
        self.set_status("Opening dedicated host server window — keep it open for 24/7 service.")
        subprocess.Popen(["cmd", "/c", "start", "JRC Host Server", str(bat)], cwd=str(BASE_DIR), shell=True)

    def pre_install_security_check(self):
        """Open login/security check from the running installed app. This is also callable after install."""
        if self.ensure_local_login_ready(open_monitor=True):
            webbrowser.open(urls()["local"] + "/owner-security-status")
            self.set_status("Opened Owner Security Status after verifying local login host.")

    def show_host_monitor(self):
        try:
            if self.host_monitor_window and self.host_monitor_window.winfo_exists():
                self.host_monitor_window.lift()
                self.host_monitor_window.refresh()
                return
        except Exception:
            pass
        self.host_monitor_window = HostMonitor(self)



    def open_local_login_gate(self):
        """Open reliable local login/setup without requiring Flask/local host."""
        self.set_status("Opening Secure Local Login. This does not require local host verification.")
        proc, log, err = launch_hidden([PYW_CMD, "-m", "app.local_login_gate"], "local_login_gate_last.log")
        if err:
            messagebox.showwarning("Local Login could not start", f"{err}\n\nLog: {log}")
            return False
        self._watch_process(proc, log, "Secure Local Login", "Secure Local Login opened. If nothing appears, open Logs and check local_login_gate_last.log.")
        return True

    def _require_business_storage(self, action: str) -> bool:
        try:
            from app.data_pipeline import resolve_paths, mode_label
            if resolve_paths().business_storage_enabled:
                return True
            messagebox.showinfo(
                "Remote Client — No Local Business Storage",
                f"This PC cannot {action}.\n\n{mode_label()}\n\n"
                "Use Mobile Links or Cloud Access from Start Center instead.",
            )
            return False
        except Exception:
            return True

    def ensure_local_login_ready(self, open_monitor: bool = True) -> bool:
        if not self._require_business_storage("run the local business server"):
            return False
        """Start local server if needed and verify the login page first.
        Login is less fragile than the full mobile endpoint chain, so this is used
        for setup and default admin/admin access.
        """
        if is_login_ready():
            return True
        set_runtime_port(find_available_port(PORT), "Auto-selected by Start Center for login-first startup.")
        missing = missing_dependencies()
        if "flask" in missing:
            self.set_status("Flask/network dependency is missing. Running Auto Repair Host first is recommended.")
            messagebox.showwarning("Repair Needed", "The local web login needs Flask/network dependencies.\n\nClick Auto Repair Host, then try Open Login again.")
            return False
        if open_monitor:
            self.show_host_monitor()
        self.set_status(f"Starting local web app for Login on port {PORT}...")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.network_server"], "shared_host_last.log", {"JRC_PORT": str(PORT)})
        if err:
            messagebox.showwarning("Login server did not launch", f"{err}\n\nLog: {log}")
            return False
        ok, msg = wait_for_login(timeout=20.0)
        if ok:
            self.set_status("Login page is ready. Default first setup login is admin / admin.")
            return True
        tail = tail_log(log)
        self.set_status("Local web app started but Login did not verify. Run Auto Repair Host.")
        messagebox.showwarning("Login Not Verified", f"The server process started, but /login did not answer.\n\nLast message: {msg}\n\nLog: {log}\n\nTry Auto Repair Host.\n\nLog tail:\n{tail[:900]}")
        return False

    def open_login_first(self):
        """Open secure login first. Local mode uses no-host desktop login; cloud mode uses cloud login."""
        cloud = get_cloud_base_url()
        if cloud:
            webbrowser.open(link_set(cloud)["base"] + "/login")
            self.set_status("Opened cloud login. Dashboard opens only after successful login.")
            return
        self.open_local_login_gate()

    def open_dashboard(self):
        """Open cloud dashboard if configured; otherwise use local login gate and Office."""
        cloud = get_cloud_base_url()
        if cloud:
            webbrowser.open(link_set(cloud)["base"] + "/")
            self.set_status("Opened cloud dashboard/login route. Role controls dashboard after sign-in.")
            return
        self.open_local_login_gate()

    def login_dashboard(self):
        cloud = get_cloud_base_url()
        if cloud:
            url = link_set(cloud)["base"] + "/login"
            self.set_status(f"Opening cloud login. Dashboard is based on the account role after login: {cloud}")
            webbrowser.open(url)
            return
        if not is_host_running():
            if messagebox.askyesno("Start local login?", "No cloud URL is set and local host is not running.\n\nStart the local host and open the login/dashboard page?"):
                self.start_host()
                def wait_login():
                    ok, msg, checks = wait_for_host(timeout=26.0)
                    def finish():
                        if ok:
                            webbrowser.open(urls()["local"] + "/login")
                        else:
                            messagebox.showwarning("Login not ready", f"Local login is not ready.\n\n{quick_test_summary(checks)}\n\n{msg}")
                    self.after(0, finish)
                threading.Thread(target=wait_login, daemon=True).start()
            return
        self.set_status("Opening local web login. Account role controls the dashboard after login.")
        webbrowser.open(urls()["local"] + "/login")

    def open_office(self):
        self.set_status("Opening Office app in the background...")
        proc, log, err = launch_hidden([PYW_CMD, "-m", "app.jr_job_manager"], "desktop_app_last.log")
        if err:
            messagebox.showwarning("Office did not launch", f"{err}\n\nLog: {log}")
        self._watch_process(proc, log, "Office app", "Office app launched. If nothing appears, open Logs from Files / Logs.")

    def start_host(self):
        if not self._require_business_storage("host business data on this PC"):
            return
        try:
            from app.host_laptop_roles import pre_start_host_check
            proceed, pre_msg = pre_start_host_check(BASE_DIR)
            if not proceed:
                choice = messagebox.askyesnocancel(
                    "Remote Host Already Running",
                    pre_msg + "\n\nYES = Start host on THIS laptop anyway (stop the other host first in practice).\n"
                    "NO = Open Connect to Remote Host instead.\n"
                    "CANCEL = Do nothing.",
                )
                if choice is None:
                    return
                if choice is False:
                    self.connect_remote_host()
                    return
        except Exception:
            pass
        if is_login_ready():
            ok, msg, checks = wait_for_host(timeout=6.0)
            self.show_host_monitor()
            self.set_status(f"Local web app is running. Login is ready. Mobile quick test: {'passed' if ok else 'needs attention'}.")
            messagebox.showinfo(
                "Local Web App Running",
                f"Login is ready now. Use admin/admin for first setup if unchanged.\n\nLogin:\n{urls()['local']}/login\n\nMobile quick test:\n{quick_test_summary(checks)}\n\nPhone connection test:\n{urls()['connect']}"
            )
            return
        set_runtime_port(find_available_port(PORT), "Auto-selected by Start Center before launching local host.")
        missing = missing_dependencies()
        if "flask" in missing:
            self.set_status("Network/mobile tools are missing. Run Auto Repair Host.")
            messagebox.showwarning("Repair Needed", "Network/mobile tools are missing.\n\nClick Auto Repair Host first, then Start Local Host again.")
            return
        self.set_status(f"Starting local web app on port {PORT}. Login will be verified first...")
        self.show_host_monitor()
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.network_server"], "shared_host_last.log", {"JRC_PORT": str(PORT)})
        if err:
            messagebox.showwarning("Host did not launch", f"{err}\n\nLog: {log}")
            return

        def verify_in_thread():
            login_ok, login_msg = wait_for_login(timeout=22.0)
            ok, msg, checks = wait_for_host(timeout=10.0, step=0.8) if login_ok else (False, login_msg, {})
            def finish():
                if login_ok:
                    self.set_status(f"Login verified. Mobile quick test: {'passed' if ok else 'needs attention'}. Login: {urls()['local']}/login")
                    if ok:
                        messagebox.showinfo(
                            "Local Host Ready",
                            f"Login and mobile endpoints verified.\n\nLogin first:\n{urls()['local']}/login\n\nPhone connection test:\n{urls()['connect']}\n\nMobile app:\n{urls()['mobile']}"
                        )
                    else:
                        messagebox.showwarning(
                            "Login Ready - Mobile Needs Attention",
                            f"The login screen is working, but not every mobile endpoint verified yet. You can still log in locally.\n\nLogin:\n{urls()['local']}/login\n\nMobile checks:\n{quick_test_summary(checks)}\n\nIf phones cannot connect, run Auto Repair Host and Allow Phone Access."
                        )
                else:
                    code = proc.poll() if proc else None
                    log_tail = tail_log(log)
                    self.set_status(f"Login did not verify. Run Auto Repair Host. Log: {log}")
                    messagebox.showwarning(
                        "Login Verification Failed",
                        "The local host process was started, but the Login page did not answer.\n\n"
                        f"Process status: {'still running' if code is None else 'stopped with code ' + str(code)}\n"
                        f"Last message: {login_msg}\n\nLog file:\n{log}\n\nRun Auto Repair Host, then try Open Login.\n\nLog tail:\n{log_tail[:1200]}"
                    )
            self.after(0, finish)
        threading.Thread(target=verify_in_thread, daemon=True).start()

    def stop_host(self):
        """Gracefully stop the local network server process."""
        from app.host_process import stop_host_process, read_host_pid
        running = is_host_running() or (read_host_pid() is not None)
        if running and not messagebox.askyesno(
            "Stop Local Host?",
            "Stop the shared host server?\n\nBusiness data is auto-saved on shutdown. Users can sign back in after restart until session timeout.",
        ):
            return
        try:
            ok, msg = stop_host_process()
            self.set_status(msg)
            if running:
                messagebox.showinfo("Host Stopped" if ok else "Stop Host", msg)
            if hasattr(self, "admin_panel"):
                self.admin_panel.refresh()
        except Exception as exc:
            messagebox.showwarning("Stop Host", str(exc))

    def connect_remote_host(self):
        """Open browser to the dedicated/other laptop host URL."""
        try:
            from app.host_laptop_roles import (
                get_remote_host_url,
                probe_host_url,
                remote_host_is_running,
                set_remote_host_url,
            )
        except Exception as exc:
            messagebox.showwarning("Remote Host", str(exc))
            return
        url = get_remote_host_url(BASE_DIR)
        if not url:
            url = simpledialog.askstring(
                "Remote Host URL",
                "Enter the other laptop's host address.\nExample: http://192.168.50.60:8765",
                parent=self,
            ) or ""
            url = set_remote_host_url(url, BASE_DIR)
        if not url:
            return
        ok, data = probe_host_url(url)
        if not ok:
            messagebox.showwarning(
                "Remote Host Not Reachable",
                f"Could not reach:\n{url}\n\n"
                "• Is the dedicated laptop on and running Start Local Host?\n"
                "• Same Wi-Fi network?\n"
                "• Correct IP address?",
            )
            return
        login = url.rstrip("/") + "/login"
        self.set_status(f"Remote host OK — opening {login}")
        webbrowser.open(login)
        messagebox.showinfo(
            "Remote Host Connected",
            f"Host is running:\n{url}\n\nVersion: {data.get('version', '?')}\n\n"
            "Sign in as ivygrows (owner) for full admin.\n"
            "Dedicated laptop local operator uses jrc_host on that PC only.",
        )

    def host_laptop_setup_wizard(self):
        """Configure this PC as office or dedicated host."""
        try:
            from app.host_laptop_roles import (
                PROFILE_DEDICATED,
                PROFILE_OWNER,
                get_host_pc_role,
                host_role_label,
                setup_pc_profile,
            )
        except Exception as exc:
            messagebox.showwarning("Host Setup", str(exc))
            return
        current = get_host_pc_role(BASE_DIR)
        choice = messagebox.askyesnocancel(
            "Host Laptop Setup",
            f"Current: {host_role_label(BASE_DIR)}\n\n"
            "YES = This is the OFFICE laptop (Cursor, Dropbox, can host OR use remote host)\n"
            "NO = This is the DEDICATED 24/7 HOST laptop (runs server; local login jrc_host)\n"
            "CANCEL = Do nothing",
        )
        if choice is None:
            return
        profile = PROFILE_OWNER if choice else PROFILE_DEDICATED
        remote_url = ""
        copy_db = ""
        host_pwd = ""
        if profile == PROFILE_OWNER:
            remote_url = simpledialog.askstring(
                "Remote Host URL (optional)",
                "If the dedicated laptop runs the host, enter its LAN URL now.\n"
                "Example: http://192.168.50.60:8765\n\nLeave blank if this PC hosts locally.",
                parent=self,
            ) or ""
        else:
            copy_db = simpledialog.askstring(
                "Copy office database? (recommended once)",
                "Paste full path to office jr_business.db to copy users/chat to host laptop.\n"
                "Example: C:\\Users\\...\\Documents\\JRC\\...\\data\\jr_business.db\n\n"
                "Leave blank for fresh host DB (jrc_host created on first start).",
                parent=self,
            ) or ""
            host_pwd = simpledialog.askstring(
                "jrc_host password (optional)",
                "Dedicated host local admin login.\nDefault: jrc_host / jrc_host\n\nLeave blank for default.",
                parent=self,
                show="*",
            ) or ""
        try:
            lines = setup_pc_profile(
                BASE_DIR,
                profile,
                remote_host_url=remote_url,
                copy_db_from=copy_db,
                host_admin_password=host_pwd,
            )
            self.set_status("Host laptop role saved.")
            if hasattr(self, "_head_pipeline"):
                try:
                    from app.data_pipeline import mode_label as pipeline_mode_label
                    from app.host_laptop_roles import host_role_label as hrl
                    self._head_pipeline.config(text=pipeline_mode_label() + " | " + hrl(BASE_DIR))
                except Exception:
                    pass
            messagebox.showinfo("Host Laptop Setup Complete", "\n".join(lines))
        except Exception as exc:
            messagebox.showwarning("Host Setup Failed", str(exc))

    def mobile_links(self):
        cloud = get_cloud_base_url()
        if cloud:
            self.set_status(f"Using Cloud Access URL: {cloud}")
            MobileWindow(self, cloud, mode="cloud")
            webbrowser.open(link_set(cloud)["connect"])
            return
        if not is_host_running():
            choice = messagebox.askyesnocancel(
                "No Host Running",
                "No local host is running and no Cloud Access URL is saved.\n\n"
                "YES = start the local same-Wi-Fi host now.\n"
                "NO = set a Cloud/Tunnel/VPN URL for remote users.\n"
                "CANCEL = do nothing.\n\n"
                "Remote users cannot connect while your PC host is off unless you use a cloud/tunnel/VPN server that stays running."
            )
            if choice is None:
                return
            if choice is False:
                self.set_cloud_url_prompt()
                return
            self.set_status("Mobile links need the shared host. Starting local host, then testing connection...")
            self.start_host()
            def wait_then_open():
                ok, msg, checks = wait_for_host(timeout=26.0, step=0.8)
                def finish():
                    if ok:
                        MobileWindow(self, None, mode="local")
                        webbrowser.open(urls()["connect"])
                    else:
                        messagebox.showwarning("Mobile Host Not Ready", f"Mobile links are not ready yet.\n\nQuick Test:\n{quick_test_summary(checks)}\n\nLast message: {msg}\n\nOpen Tools / Repair > Run Host Quick Test for details.")
                self.after(0, finish)
            threading.Thread(target=wait_then_open, daemon=True).start()
        else:
            ok, msg, checks = wait_for_host(timeout=4.0)
            if ok:
                MobileWindow(self, None, mode="local")
                webbrowser.open(urls()["connect"])
            else:
                messagebox.showwarning("Host Needs Attention", f"Host is running but mobile quick test did not fully pass.\n\n{quick_test_summary(checks)}\n\n{msg}")

    def worker_forms(self):
        cloud = get_cloud_base_url()
        if cloud:
            links = link_set(cloud)
            body = f"Cloud Worker Signup / Account Request:\n{links['register']}\n\nCloud Job Application / Insurance Onboarding:\n{links['apply']}\n\nThese links work from other locations only if the cloud/tunnel/VPN host is running."
            messagebox.showinfo("Worker Forms - Cloud Mode", body)
            webbrowser.open(links["apply"])
            return
        if not is_host_running():
            messagebox.showinfo("Choose Access Mode", "For workers/applicants from other locations, set Cloud Access first.\n\nFor same-Wi-Fi testing, click Start Local Host first.")
            return
        u = urls()
        body = f"Worker Signup / Account Request:\n{u['register']}\n\nJob Application / Insurance Onboarding:\n{u['apply']}"
        messagebox.showinfo("Worker Forms", body)
        webbrowser.open(u["apply"])

    def set_cloud_url_prompt(self):
        current = get_cloud_base_url()
        value = simpledialog.askstring(
            "Set Cloud Access URL",
            "Enter the HTTPS cloud/tunnel/VPN base URL for your JRC Manager.\n\nExample: https://your-jrc-manager.example.com\n\nLeave blank to clear.",
            initialvalue=current,
            parent=self,
        )
        if value is None:
            return
        value = normalize_base_url(value)
        if value and not value.startswith("https://"):
            if not messagebox.askyesno("HTTP warning", "HTTPS is strongly recommended for remote users and secure cookies. Save this non-HTTPS URL anyway?"):
                return
        saved = set_cloud_base_url(value)
        if saved:
            self.set_status(f"Cloud Access URL saved: {saved}")
            messagebox.showinfo("Cloud Access Saved", f"Saved Cloud Access URL:\n{saved}\n\nMobile Links will now use cloud links even when your PC host is off.")
        else:
            self.set_status("Cloud Access URL cleared.")
            messagebox.showinfo("Cloud Access Cleared", "Cloud Access URL cleared. Mobile Links will use local host mode again.")

    def cloud_options(self):
        cloud = get_cloud_base_url()
        status = f"Saved Cloud Access URL: {cloud}" if cloud else "No Cloud Access URL saved yet."
        body = (
            "Remote users can connect while your PC host is off only when JRC Manager is running on a separate cloud/VPS/tunnel/VPN host.\n\n"
            f"Current status:\n{status}\n\n"
            "Why local laptop hosting may fail:\n"
            "- Windows Firewall may block phones.\n"
            "- Router/NAT does not allow outside internet users to reach your laptop.\n"
            "- Laptop sleep mode stops the host.\n"
            "- Antivirus/network privacy settings can block Flask/Python.\n"
            "- IP addresses change.\n\n"
            "Best staged plan for J&R:\n"
            "1. Use Open Office locally for business records.\n"
            "2. Use Start Local Host only for same-Wi-Fi or VPN testing.\n"
            "3. Deploy cloud_hosting with HTTPS for real remote use.\n"
            "4. Save the Cloud Access URL here.\n"
            "5. Share only /mobile, /register, or /apply links with approved people.\n\n"
            "Included folder:\n"
            f"{BASE_DIR / 'cloud_hosting'}\n"
        )
        HelpWindow(self, "Cloud Access for Remote Users", body)
        if messagebox.askyesno("Cloud Access", "Set or edit your Cloud Access URL now?"):
            self.set_cloud_url_prompt()
        else:
            try:
                open_path(BASE_DIR / "cloud_hosting")
            except Exception:
                pass

    def tools_window(self):
        win = tk.Toplevel(self)
        win.title("Tools and Repair")
        win.geometry("520x440")
        win.configure(bg=BG)
        tk.Label(win, text="Tools and Repair", bg=BG, fg=TEXT, font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=18, pady=(16, 6))
        tk.Label(win, text="These are heavier tools. They run in the background and save reports/logs.", bg=BG, fg=MUTED, font=("Segoe UI", 10), wraplength=460, justify="left").pack(anchor="w", padx=18, pady=(0, 12))
        items = [
            ("Background Troubleshooter (Full Auto)", self.run_background_troubleshooter),
            ("Run System Check", self.run_system_check),
            ("Run Full QA Test", self.run_full_qa),
            ("Permission View Check", self.run_permission_view_check),
            ("Security Perspective Audit", self.run_security_audit),
            ("Access Mode Check", self.run_access_mode_check),
            ("Dashboard Role Check", self.run_dashboard_role_check),
            ("Customer Request Final Check", self.run_customer_request_final_check),
            ("Final Program Verify", self.run_final_verify),
            ("Internet / Cloud Security Verify", self.run_internet_cloud_verify),
            ("Admin Security Final Check", self.run_admin_security_final_check),
            ("Login/Install System Check", self.run_login_install_system_check),
            ("Self Setup + Verify", self.self_setup_verify),
            ("Cloud Deploy Check", self.run_cloud_deploy_check),
            ("Cloud Primary Final Check", self.run_cloud_primary_final_check),
            ("Primary Live Server Check", self.run_primary_live_server_check),
            ("v6 Final Readiness", self.run_v6_final_readiness),
            ("Run Host Quick Test", self.run_host_quick_test),
            ("Auto Host Repair", self.auto_host_repair),
            ("Repair Features", self.repair_features),
            ("Allow Phone Access", self.allow_firewall),
            ("Emergency Access Check", self.run_emergency_access_check),
            ("Full Live Update", self.run_live_full_update),
            ("Developer Tools Console", self.developer_tools_window),
            ("Open Logs", lambda: open_path(LOG_DIR)),
            ("Open Exports", lambda: open_path(EXPORT_DIR)),
        ]
        for label, cmd in items:
            tk.Button(win, text=label, command=cmd, bg=BUTTON, fg=TEXT, relief="flat", font=("Segoe UI", 11, "bold"), padx=10, pady=9).pack(fill="x", padx=18, pady=5)

    def developer_tools_window(self):
        if not self._admin_developer_pc():
            messagebox.showwarning("Admin Only", "Developer tools are for Owner Master / admin PCs only.")
            return
        try:
            from app.program_manifest import DEVELOPER_TOOLS
        except Exception:
            DEVELOPER_TOOLS = ()
        win = tk.Toplevel(self)
        win.title("Admin Developer Tools")
        win.geometry("620x560")
        win.minsize(480, 360)
        win.configure(bg=BG)
        tk.Label(win, text="Admin Developer Tools", bg=BG, fg=ACCENT, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=18, pady=(14, 4))
        tk.Label(
            win,
            text="Full bells and whistles for admin users. All tools run hidden (no CMD) and save logs under logs/ and exports/.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 10))
        outer = tk.Frame(win, bg=BG)
        outer.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scroll = theme.dark_scrollbar(outer, command=canvas.yview) if theme else tk.Scrollbar(outer, command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def run_script(rel: str, log_stem: str):
            script = BASE_DIR / rel
            if not script.exists():
                messagebox.showwarning("Missing", f"Not found:\n{script}")
                return
            self.set_status(f"Running {script.name}...")
            proc, log, err = launch_hidden([PY_CMD, str(script)], f"{log_stem}_last.log")
            if err:
                messagebox.showwarning("Could not start", err)
                return
            self._watch_process(proc, log, script.stem, f"{script.stem} running. Log: {log}")

        for title, rel, desc in DEVELOPER_TOOLS:
            row = tk.Frame(inner, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
            row.pack(fill="x", padx=8, pady=5)
            top = tk.Frame(row, bg=CARD)
            top.pack(fill="x", padx=12, pady=(10, 0))
            tk.Label(top, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left")
            tk.Button(
                top,
                text="Run",
                command=lambda r=rel, s=Path(rel).stem: run_script(r, s),
                bg=ACCENT,
                fg="#000",
                relief="flat",
                padx=10,
                pady=4,
                font=("Segoe UI", 9, "bold"),
            ).pack(side="right")
            tk.Label(row, text=f"{desc}\n{rel}", bg=CARD, fg=MUTED, font=("Segoe UI", 9), wraplength=520, justify="left").pack(
                anchor="w", padx=12, pady=(4, 10)
            )

        extra = [
            ("Tools / Repair (all)", self.tools_window),
            ("Open LIVE_UPDATE_REPORT.txt", lambda: open_path(BASE_DIR / "LIVE_UPDATE_REPORT.txt")),
            ("Open INSTALL_SETUP_REPORT.txt", lambda: open_path(BASE_DIR / "INSTALL_SETUP_REPORT.txt")),
        ]
        for label, cmd in extra:
            tk.Button(inner, text=label, command=cmd, bg=BUTTON, fg=TEXT, relief="flat", padx=10, pady=8).pack(fill="x", padx=8, pady=3)

    def run_live_full_update(self):
        if not self._admin_developer_pc():
            messagebox.showwarning("Admin Only", "Full live update is for Owner Master / admin PCs.")
            return
        self.set_status("Full live update running — sync, verify, log, save (see LIVE_UPDATE_REPORT.txt)...")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "live_full_update.py")], "live_full_update_last.log")
        if err:
            messagebox.showwarning("Live update could not start", err)
            return
        self._watch_process(proc, log, "Full Live Update", "Live update running. Report: LIVE_UPDATE_REPORT.txt")

    def run_office_records_sync(self):
        if not self._admin_developer_pc():
            messagebox.showwarning("Admin Only", "Office sync is for Owner Master / admin PCs.")
            return
        self.set_status("Office records sync — job register, payroll import/export, office CSV merge...")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.office_records_sync"], "office_sync_last.log")
        if err:
            messagebox.showwarning("Office sync could not start", err)
            return
        self._watch_process(proc, log, "Office Records Sync", "See logs/office_sync_last.log and exports/office_sync/")

    def run_sync_business_workspace(self):
        if not self._admin_developer_pc():
            messagebox.showwarning("Admin Only", "Workspace sync is for Owner Master / admin PCs.")
            return
        self.set_status("Syncing ONE business workspace (Dropbox)...")
        sync_ps1 = BASE_DIR / "scripts" / "Sync-JRCBusinessFolders.ps1"
        refresh_ps1 = BASE_DIR / "scripts" / "Refresh-ReadableBusinessReports.ps1"
        if sync_ps1.is_file():
            proc, log, err = launch_hidden(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(sync_ps1)],
                "workspace_sync_last.log",
            )
            if err:
                messagebox.showwarning("Workspace sync could not start", err)
                return
            self._watch_process(
                proc,
                log,
                "Business Workspace Sync",
                "ONE workspace: phone Cursor + Manager + office CSVs.\n"
                "Includes Refresh-ReadableBusinessReports.\n"
                "Phone verify: 00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt",
            )
            return
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.phone_cursor_workspace", "--deploy"], "workspace_sync_last.log")
        if err:
            messagebox.showwarning("Workspace sync could not start", err)
            return
        self._watch_process(proc, log, "Business Workspace Sync", "See logs/workspace_sync_last.log")

    def run_phone_cursor_dropbox_setup(self):
        """Legacy name — same as run_sync_business_workspace."""
        self.run_sync_business_workspace()

    def run_phase_verification(self):
        if not self._admin_developer_pc():
            messagebox.showwarning("Admin Only", "Phase verification is for Owner Master / admin PCs.")
            return
        self.set_status("Running phase verification...")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.run_phase_verification"], "phase_verify_last.log")
        if err:
            messagebox.showwarning("Phase verify could not start", err)
            return
        self._watch_process(proc, log, "Phase Verification", "Report: PHASE_VERIFICATION_REPORT.txt")

    def run_developer_status(self):
        self.set_status("Writing admin developer status report...")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.admin_developer_suite", "--status"], "developer_status_last.log")
        if err:
            messagebox.showwarning("Could not start", err)
            return
        self._watch_process(proc, log, "Developer Status", "Report saved in exports/")

    def run_verify_bundle(self):
        self.set_status("Running developer verify bundle...")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.admin_developer_suite", "--verify-bundle"], "verify_bundle_last.log")
        if err:
            messagebox.showwarning("Could not start", err)
            return
        self._watch_process(proc, log, "Verify Bundle", "Bundle report in exports/")

    def open_admin_database(self):
        if not self._require_business_storage("open the admin database editor"):
            return
        self._open_admin_url("/admin/database", "Admin Database Editor")

    def open_admin_accounts(self):
        if not self._require_business_storage("open the account database editor"):
            return
        self._open_admin_url("/admin/database/accounts", "Account Database Editor")

    def _open_admin_url(self, path: str, label: str):
        url = urls()["local"] + path
        if is_host_running():
            webbrowser.open(url)
            self.set_status(f"Opened {label}.")
            return
        if messagebox.askyesno("Start Host", f"Start local host to open {label}?"):
            self.start_host()

            def wait_open():
                for _ in range(40):
                    if is_host_running():
                        webbrowser.open(url)
                        self.set_status(f"{label} opened.")
                        return
                    time.sleep(0.5)
                messagebox.showwarning("Not Ready", f"Start host failed. Try Admin & security → Start Local Host, then open {label} again.")

            threading.Thread(target=wait_open, daemon=True).start()

    def run_initialize_install(self):
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "initialize_install.py")], "initialize_install_last.log")
        if err:
            messagebox.showwarning("Could not start", err)
            return
        self._watch_process(proc, log, "Initialize Install", f"Install initializer log: {log}")

    def seed_emergency_key(self):
        ps1 = BASE_DIR / "scripts" / "Seed-OwnerEmergencyKey.ps1"
        if not ps1.exists():
            messagebox.showwarning("Missing", f"Not found:\n{ps1}")
            return
        proc, log, err = launch_hidden(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(ps1), "-InstallDir", str(BASE_DIR)],
            "seed_emergency_key_last.log",
        )
        if err:
            messagebox.showwarning("Could not start", err)
            return
        self.set_status("Emergency mastery key seed running...")
        self._watch_process(proc, log, "Seed Emergency Key", f"Log: {log}")

    def open_installer_source(self):
        src = BASE_DIR / "INSTALLER_SOURCE.txt"
        if src.exists():
            path = Path(src.read_text(encoding="utf-8").strip())
            if path.exists():
                open_path(path)
                self.set_status(f"Opened installer source: {path}")
                return
        open_path(BASE_DIR)
        self.set_status("Opened program folder (INSTALLER_SOURCE.txt not set).")

    def open_web_dashboard(self):
        """Start web server if needed and open the glass browser UI."""
        if launch_web_dashboard is None:
            messagebox.showwarning("Unavailable", "Web dashboard helper could not load.")
            return
        self.set_status("Finding a free port and opening Web Dashboard...")
        ok, msg = launch_web_dashboard("/login")
        self.set_status(msg)
        if not ok:
            messagebox.showinfo("Web Dashboard", msg + "\n\nIf the page fails, another program may have been using port 8765 — JRC will try 8766, 8767, etc.")

    def primary_live_server(self):
        self.set_status("Opening Primary Live Server readiness page. Use this for the recommended 24/7 cloud setup.")
        cloud = get_cloud_base_url()
        if cloud:
            webbrowser.open(cloud.rstrip('/') + "/primary-live-readiness")
        else:
            self.set_cloud_url_prompt()
            messagebox.showinfo("Cloud URL Needed", "Set your Cloud Access URL after deploying the live server. Until then, this opens the local cloud setup notes if the local host is running.")
            if is_host_running() or is_login_ready():
                webbrowser.open(urls()["local"] + "/primary-live-readiness")

    def run_primary_live_server_check(self):
        self.set_status("Primary Live Server Check started. It verifies recommended cloud provider files, data paths, health checks, and security settings.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "primary_live_server_check.py")], "primary_live_server_check_last.log")
        if err:
            messagebox.showwarning("Primary Live Server Check could not start", err)
            return
        self._watch_process(proc, log, "Primary Live Server Check", f"Primary Live Server Check is running. Log: {log}")

    def first_setup_login(self):
        self.set_status("First Setup / Login started. It opens the secure app login, not the installer.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "first_run_login_setup.py")], "first_setup_login_last.log")
        if err:
            messagebox.showwarning("First Setup could not start", err)
            return
        self._watch_process(proc, log, "First Setup / Login", f"First Setup / Login is running. Log: {log}")

    def self_setup_verify(self):
        self.set_status("Self Setup + Verify started. It will run safe checks and write a report.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "self_setup_verify.py")], "self_setup_verify_last.log")
        if err:
            messagebox.showwarning("Self Setup + Verify could not start", err)
            return
        self._watch_process(proc, log, "Self Setup + Verify", f"Self Setup + Verify is running. Log: {log}")

    def run_internet_cloud_verify(self):
        self.set_status("Internet / Cloud Security Verify started. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "internet_cloud_security_verify.py")], "internet_cloud_security_verify_last.log")
        if err:
            messagebox.showwarning("Internet / Cloud Security Verify could not start", err)
            return
        self._watch_process(proc, log, "Internet / Cloud Security Verify", f"Internet / Cloud Security Verify is running. Log: {log}")


    def run_login_install_system_check(self):
        self.set_status("Login/Install System Check started. It verifies no-host login, admin preservation, and installer handoff.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "login_install_system_check.py")], "login_install_system_check_last.log")
        if err:
            messagebox.showwarning("Login/Install System Check could not start", err)
            return
        self._watch_process(proc, log, "Login/Install System Check", f"Login/Install System Check is running. Log: {log}")

    def run_admin_security_final_check(self):
        self.set_status("Admin Security Final Check started. It verifies default admin cannot be used remotely after setup.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "admin_security_final_check.py")], "admin_security_final_check_last.log")
        if err:
            messagebox.showwarning("Admin Security Check could not start", err)
            return
        self._watch_process(proc, log, "Admin Security Final Check", f"Admin Security Final Check is running. Log: {log}")

    def run_customer_request_final_check(self):
        self.set_status("Customer Request Final Check started. It verifies customer forms, request fields, and privacy separation.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "customer_request_final_check.py")], "customer_request_final_check_last.log")
        if err:
            messagebox.showwarning("Customer Request Check could not start", err)
            return
        self._watch_process(proc, log, "Customer Request Final Check", f"Customer Request Final Check is running. Log: {log}")

    def run_background_troubleshooter(self):
        self.set_status("Running background troubleshooter...")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.background_troubleshooter"], "background_troubleshooter_last.log")
        if err:
            messagebox.showwarning("Troubleshooter could not start", err)
            return
        self._watch_process(proc, log, "Background Troubleshooter", "Report saved to exports folder. Open Files / Logs if needed.")

    def run_emergency_access_check(self):
        self.set_status("Emergency access check started...")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "emergency_access_check.py"), str(BASE_DIR)], "emergency_access_check_last.log")
        if err:
            messagebox.showwarning("Could not start", err)
            return
        self._watch_process(proc, log, "Emergency Access Check", f"Log: {log}")

    def run_system_check(self):
        self.set_status("System Check started in background. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.system_check"], "system_check_last.log")
        if err:
            messagebox.showwarning("System Check could not start", err)
            return
        self._watch_process(proc, log, "System Check", f"System Check is running. Log: {log}")

    def run_full_qa(self):
        self.set_status("Full QA Test started in background. This can take a moment.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "full_program_qa.py")], "full_qa_last.log")
        if err:
            messagebox.showwarning("Full QA could not start", err)
            return
        self._watch_process(proc, log, "Full QA Test", f"Full QA Test is running. Log: {log}")


    def run_permission_view_check(self):
        self.set_status("Permission View Check started in background. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "permission_view_check.py")], "permission_view_check_last.log")
        if err:
            messagebox.showwarning("Permission View Check could not start", err)
            return
        self._watch_process(proc, log, "Permission View Check", f"Permission View Check is running. Log: {log}")


    def run_security_audit(self):
        self.set_status("Security Perspective Audit started in background. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "security_perspective_audit.py")], "security_perspective_audit_last.log")
        if err:
            messagebox.showwarning("Security Audit could not start", err)
            return
        self._watch_process(proc, log, "Security Perspective Audit", f"Security Perspective Audit is running. Log: {log}")

    def run_access_mode_check(self):
        self.set_status("Access Mode Check started in background. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "access_mode_check.py")], "access_mode_check_last.log")
        if err:
            messagebox.showwarning("Access Mode Check could not start", err)
            return
        self._watch_process(proc, log, "Access Mode Check", f"Access Mode Check is running. Log: {log}")

    def run_dashboard_role_check(self):
        self.set_status("Dashboard Role Check started in background. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "dashboard_role_check.py")], "dashboard_role_check_last.log")
        if err:
            messagebox.showwarning("Dashboard Role Check could not start", err)
            return
        self._watch_process(proc, log, "Dashboard Role Check", f"Dashboard Role Check is running. Log: {log}")


    def run_final_verify(self):
        self.set_status("Final Program Verify started in background. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "final_program_verify.py")], "final_program_verify_last.log")
        if err:
            messagebox.showwarning("Final Program Verify could not start", err)
            return
        self._watch_process(proc, log, "Final Program Verify", f"Final Program Verify is running. Log: {log}")

    def run_cloud_deploy_check(self):
        self.set_status("Cloud Deploy Check started in background. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "cloud_deploy_check.py")], "cloud_deploy_check_last.log")
        if err:
            messagebox.showwarning("Cloud Deploy Check could not start", err)
            return
        self._watch_process(proc, log, "Cloud Deploy Check", f"Cloud Deploy Check is running. Log: {log}")

    def run_cloud_primary_final_check(self):
        self.set_status("Cloud Primary Final Check started. It verifies v7.1 cloud-first structure, persistent data paths, and first owner login rules.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "cloud_primary_final_check.py")], "cloud_primary_final_check_last.log")
        if err:
            messagebox.showwarning("Cloud Primary Final Check could not start", err)
            return
        self._watch_process(proc, log, "Cloud Primary Final Check", f"Cloud Primary Final Check is running. Log: {log}")

    def run_v6_final_readiness(self):
        self.set_status("v6 Final Readiness started. It checks login perspectives, cloud files, Dropbox/file sources, repair tools, and security markers.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "v6_final_readiness.py")], "v6_final_readiness_last.log")
        if err:
            messagebox.showwarning("v6 Final Readiness could not start", err)
            return
        self._watch_process(proc, log, "v6 Final Readiness", f"v6 Final Readiness is running. Log: {log}")

    def run_host_quick_test(self):
        self.set_status("Running host quick test. If host is not running, this will explain what failed.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "host_quick_test.py")], "host_quick_test_last.log")
        if err:
            messagebox.showwarning("Host Quick Test could not start", err)
            return
        self._watch_process(proc, log, "Host Quick Test", f"Host Quick Test is running. Log: {log}")


    def run_host_login_verify(self):
        self.set_status("Running Host Login Verify...")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "host_login_verify.py")], "host_login_verify_last.log")
        if err:
            messagebox.showwarning("Host Login Verify did not launch", f"{err}\n\nLog: {log}")
        else:
            self._watch_process(proc, log, "Host Login Verify", "Host Login Verify is running. Check exports for the report.")

    def auto_host_repair(self):
        self.set_status("Auto Host Repair started. It will read logs, check the port, and write a report.")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.auto_host_repair"], "auto_host_repair_last.log")
        if err:
            messagebox.showwarning("Auto Host Repair could not start", err)
            return
        def finish_check():
            code = proc.poll() if proc else None
            if code is None:
                self.set_status(f"Auto Host Repair is still running. Log: {log}")
                self.after(2500, finish_check)
                return
            # Reload saved port after repair; the repair tool may have selected a better port.
            set_runtime_port(get_saved_port(), "Reloaded after Auto Host Repair.")
            self.set_status(f"Auto Host Repair finished. Current local host port: {PORT}. Log: {log}")
            try:
                messagebox.showinfo("Auto Host Repair Complete", "Auto Host Repair finished.\n\nCurrent local host port: " + str(PORT) + "\n\nLog:\n" + str(log) + "\n\nOpen Exports for the full repair report.")
            except Exception:
                pass
        self.after(2500, finish_check)

    def repair_features(self):
        self.set_status("Repair Features started in background. This may take a few minutes if internet is slow.")
        proc, log, err = launch_hidden([PY_CMD, "-m", "app.dependency_tools"], "dependency_repair_last.log")
        if err:
            messagebox.showwarning("Repair could not start", err)
            return
        self._watch_process(proc, log, "Repair Features", f"Repair Features is running. Log: {log}")

    def allow_firewall(self):
        helper = BASE_DIR / "ALLOW_LAN_FIREWALL_ACCESS.bat"
        if not helper.exists():
            messagebox.showwarning("Missing helper", "ALLOW_LAN_FIREWALL_ACCESS.bat was not found.")
            return
        messagebox.showinfo("Allow Phone Access", "Windows may ask for Administrator approval. This allows trusted Wi-Fi/VPN devices to reach port 8765.")
        open_path(helper)

    def open_business_workspace(self):
        try:
            from app.jrc_workspace import WORKSPACE_NAME, ensure_unified_workspace

            rep = ensure_unified_workspace(BASE_DIR)
            path = rep.get("workspace")
            if path:
                open_path(Path(path))
                self.set_status(f"Opened unified workspace: {WORKSPACE_NAME}")
                return
        except Exception:
            pass
        fallback = Path(
            r"C:\Users\enrag\Dropbox\All Files\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
            r"\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
        )
        guide = Path(r"C:\Users\enrag\Dropbox\All Files\OPEN_JRC_BUSINESS_HERE.txt")
        if guide.exists():
            open_path(guide)
        if fallback.exists():
            open_path(fallback)
            self.set_status("Opened business workspace folder.")
        else:
            messagebox.showwarning("Not found", f"Workspace not found:\n{fallback}\n\nRun Sync Business Workspace first.")

    def open_dropbox_business(self):
        self.open_business_workspace()

    def print_local_file(self):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Print to Phoswift A42",
            filetypes=[
                ("Printable", "*.pdf;*.txt"),
                ("PDF", "*.pdf"),
                ("Text", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self.set_status(f"Printing: {Path(path).name}")
        try:
            from app.local_print import print_file, list_printers

            ok, msg = print_file(path)
            if ok:
                messagebox.showinfo("Print sent", msg)
                self.set_status("Print job sent.")
            else:
                printers = ", ".join(list_printers()) or "none"
                messagebox.showerror(
                    "Print failed",
                    f"{msg}\n\nPrinters seen: {printers}\n\n"
                    "If USB is unplugged: plug in A42, turn phone Bluetooth off, then run:\n"
                    "tools\\Bind-Phoswift-A42.ps1 as Administrator",
                )
                self.set_status("Print failed — see message.")
        except Exception as exc:
            messagebox.showerror("Print error", str(exc))
            self.set_status("Print error.")

    def files_window(self):
        win = tk.Toplevel(self)
        win.title("Files, Logs, and Help")
        win.geometry("500x430")
        win.configure(bg=BG)
        tk.Label(win, text="Files, Logs, and Help", bg=BG, fg=TEXT, font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=18, pady=(16, 6))
        tk.Label(win, text="If a button appears to do nothing, open Logs and check the newest *_last.log file.", bg=BG, fg=MUTED, font=("Segoe UI", 10), wraplength=440, justify="left").pack(anchor="w", padx=18, pady=(0, 12))
        items = [
            ("Print File to A42", self.print_local_file),
            ("Open Business Workspace", self.open_business_workspace),
            ("Open Program Folder", lambda: open_path(BASE_DIR)),
            ("Open Logs Folder", lambda: open_path(LOG_DIR)),
            ("Open Exports Folder", lambda: open_path(EXPORT_DIR)),
            ("Open Backups Folder", lambda: open_path(BASE_DIR / "backups")),
            ("Quick Help", self.quick_help),
        ]
        for label, cmd in items:
            tk.Button(win, text=label, command=cmd, bg=BUTTON, fg=TEXT, relief="flat", font=("Segoe UI", 11, "bold"), padx=10, pady=9).pack(fill="x", padx=18, pady=5)

    def quick_help(self):
        HelpWindow(self, "Quick Help", "Normal use:\n1. Click Open Office.\n2. Manage jobs, invoices, payroll, files, and bookkeeping there.\n\nMobile/users:\n1. Click Start Host.\n2. Click Mobile Links.\n3. Open Connection Test on the phone first.\n\nIf a button does nothing:\n1. Open Files / Logs.\n2. Open Logs Folder.\n3. Check desktop_app_last.log or shared_host_last.log.\n\nUse Secure Local Login after install. It does not require local host verification. Device remembering is opt-in only and expires after 90 days. Heavy tools are in Tools / Repair, and Self Setup + Verify can run safe checks automatically.")


def main() -> None:
    try:
        from app.desktop_shortcuts import ensure_desktop_shortcuts_async, read_installer_source

        ensure_desktop_shortcuts_async(BASE_DIR, read_installer_source(BASE_DIR))
    except Exception:
        pass
    try:
        from app.startup_setup import launch_ensure_venv_hidden, evaluate_setup_state

        action, _ = evaluate_setup_state(BASE_DIR)
        if action == "need_venv":
            launch_ensure_venv_hidden(BASE_DIR)
    except Exception:
        pass
    try:
        from app.install_live_sync import sync_from_master_if_available

        sync_from_master_if_available(BASE_DIR)
    except Exception:
        pass
    try:
        from app.local_login_gate import require_blocking_login

        if not require_blocking_login("Start Center"):
            return
    except Exception as exc:
        try:
            from app.install_setup_log import log_event

            log_event(BASE_DIR, "LoginGate", f"Start Center gate failed: {exc}", level="ERROR", step="login_gate")
        except Exception:
            pass
        messagebox.showerror(APP_NAME, f"Login required but gate failed: {exc}")
        return
    StartCenter().mainloop()


if __name__ == "__main__":
    main()

# v7.1 primary-live note: final package includes cloud_primary_final_check.py for live deployment readiness.
