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
except Exception:
    missing_dependencies = lambda: []
    status_text = lambda: "Dependency status unavailable."
    install_optional_dependencies = lambda timeout=300: (False, "Dependency repair unavailable.")

APP_NAME = "J and R Construction Manager"
APP_VERSION = "7.1 Primary Live Reliable Business Edition"
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
        LOCAL_HOST_SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


PORT = get_saved_port()

BG = "#07141f"
PANEL = "#0b1f2f"
CARD = "#12283a"
BORDER = "#2f4a60"
TEXT = "#f8fafc"
MUTED = "#d7e3ee"
DIM = "#9eb4c7"
ACCENT = "#14b8a6"
INFO = "#38bdf8"
WARN = "#f59e0b"
DANGER = "#ef4444"
BUTTON = "#1d3a52"
BUTTON_GREEN = "#14b8a6"


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


def find_available_port(start_port: int = DEFAULT_PORT, attempts: int = 12) -> int:
    # Prefer the saved/default port if it is free or already serving JRC. If it is occupied
    # by a non-JRC process, move to the next free port so the program can still host.
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


class StartCenter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("860x620")
        self.minsize(760, 560)
        self.configure(bg=BG)
        self.status_var = tk.StringVar(value="Ready. Click Open Office for normal business work.")
        self.host_monitor_window = None
        self._cards: list[tk.Label] = []
        try:
            ico = BASE_DIR / "assets" / "j_and_r_manager_icon.ico"
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass
        self._build()
        self.bind("<Configure>", self._on_resize)

    def set_status(self, msg: str) -> None:
        self.status_var.set(msg)
        self.update_idletasks()

    def _build(self):
        outer = tk.Frame(self, bg=BG, padx=18, pady=16)
        outer.pack(fill="both", expand=True)
        header = tk.Frame(outer, bg=PANEL, padx=18, pady=12, highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x", pady=(0, 12))
        tk.Label(header, text="J & R Construction Manager", fg=TEXT, bg=PANEL, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(header, text=f"Owned and operated by {OWNER}  •  {BUSINESS}  •  v{APP_VERSION}", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        tk.Label(header, text="Lightweight Start Center: normal buttons open fast; heavy checks run only from Tools.", fg=INFO, bg=PANEL, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 0))

        # Scrollable action area. Earlier builds used a fixed grid; on smaller
        # screens the lower card buttons could be clipped or not appear. This
        # canvas keeps every dashboard/startup button visible and reachable.
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=BG)
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        def _sync_canvas_width(event):
            try:
                canvas.itemconfigure(window_id, width=event.width)
            except Exception:
                pass
        canvas.bind("<Configure>", _sync_canvas_width)
        def _wheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
        canvas.bind_all("<MouseWheel>", _wheel)
        body.grid_columnconfigure(0, weight=1, uniform="menu")
        body.grid_columnconfigure(1, weight=1, uniform="menu")
        cards = [
            ("Secure Local Login", "Reliable login/setup with no local host required. Use admin/admin only on first setup, then change it.", self.open_login_first, "primary"),
            ("Open Dashboard", "After local login, open Office or cloud/browser dashboard. Local host is optional.", self.open_dashboard, "info"),
            ("Open Office", "Daily local desktop work: jobs, invoices, costs, payroll, files.", self.open_office, "normal"),
            ("Start Local Host", "Starts the local web server and verifies login first, then mobile tools. Same-Wi-Fi/VPN testing only.", self.start_host, "info"),
            ("Host Monitor", "Watch server status, login readiness, phone links, port, and quick tools.", self.show_host_monitor, "normal"),
            ("Auto Repair Host", "Automatically reads logs, checks dependencies/ports/settings, and fixes safe host issues.", self.auto_host_repair, "warn"),
            ("Self Setup + Verify", "Runs safe setup and verification checks after login/setup.", self.self_setup_verify, "warn"),
            ("Primary Live Server", "Recommended 24/7 cloud setup, health checks, persistent data, and deployment checklist.", self.primary_live_server, "primary"),
            ("Cloud Access", "Remote users connect here when your PC host is off.", self.cloud_options, "info"),
            ("Mobile Links", "Uses cloud URL when set; otherwise starts/verifies local host.", self.mobile_links, "normal"),
            ("Worker Forms", "Account signup, customer request, and job application links.", self.worker_forms, "normal"),
            ("Tools / Repair", "System Check, Host Test, Final Verify, firewall, logs.", self.tools_window, "warn"),
            ("Files / Logs", "Open exports, backups, logs, program folder, and help.", self.files_window, "normal"),
        ]
        for i, item in enumerate(cards):
            self._card(body, i // 2, i % 2, *item)
        footer = tk.Frame(outer, bg=PANEL, padx=12, pady=8, highlightthickness=1, highlightbackground=BORDER)
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(footer, textvariable=self.status_var, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), wraplength=800, justify="left").pack(anchor="w")

    def _card(self, parent, row, col, title, desc, command, tone="normal"):
        frame = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER, padx=14, pady=12)
        frame.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)
        parent.grid_rowconfigure(row, weight=0, minsize=118)
        frame.grid_columnconfigure(0, weight=1)
        color = ACCENT if tone == "primary" else INFO if tone == "info" else WARN if tone == "warn" else TEXT
        tk.Label(frame, text=title, bg=CARD, fg=color, font=("Segoe UI", 14, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        desc_lbl = tk.Label(frame, text=desc, bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="nw", justify="left", wraplength=320)
        desc_lbl.grid(row=1, column=0, sticky="nsew", pady=(5, 10))
        btn_bg = BUTTON_GREEN if tone == "primary" else BUTTON
        btn_fg = "#04130a" if tone == "primary" else TEXT
        tk.Button(frame, text="Open", command=command, bg=btn_bg, fg=btn_fg, relief="flat", bd=0, font=("Segoe UI", 10, "bold"), padx=10, pady=10, cursor="hand2").grid(row=2, column=0, sticky="ew", ipady=2)
        self._cards.append(desc_lbl)

    def _on_resize(self, event=None):
        width = max(self.winfo_width(), 760)
        wrap = max(250, min(390, int((width - 130) / 2) - 35))
        for desc in self._cards:
            try:
                desc.configure(wraplength=wrap)
            except Exception:
                pass

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
        proc, log, err = launch_hidden([PYW_CMD, str(BASE_DIR / "app" / "local_login_gate.py")], "local_login_gate_last.log")
        if err:
            messagebox.showwarning("Local Login could not start", f"{err}\n\nLog: {log}")
            return False
        self._watch_process(proc, log, "Secure Local Login", "Secure Local Login opened. If nothing appears, open Logs and check local_login_gate_last.log.")
        return True

    def ensure_local_login_ready(self, open_monitor: bool = True) -> bool:
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
        proc, log, err = launch_hidden([PYW_CMD, str(BASE_DIR / "app" / "jr_job_manager.py")], "desktop_app_last.log")
        if err:
            messagebox.showwarning("Office did not launch", f"{err}\n\nLog: {log}")
        self._watch_process(proc, log, "Office app", "Office app launched. If nothing appears, open Logs from Files / Logs.")

    def start_host(self):
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
            ("Open Logs", lambda: open_path(LOG_DIR)),
            ("Open Exports", lambda: open_path(EXPORT_DIR)),
        ]
        for label, cmd in items:
            tk.Button(win, text=label, command=cmd, bg=BUTTON, fg=TEXT, relief="flat", font=("Segoe UI", 11, "bold"), padx=10, pady=9).pack(fill="x", padx=18, pady=5)



    def primary_live_server(self):
        self.set_status("Opening Primary Live Server readiness page. Use this for the recommended 24/7 cloud setup.")
        cloud = self.get_cloud_url()
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

    def run_system_check(self):
        self.set_status("System Check started in background. Report will save to exports/logs.")
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "system_check.py")], "system_check_last.log")
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
        proc, log, err = launch_hidden([PY_CMD, str(BASE_DIR / "app" / "auto_host_repair.py")], "auto_host_repair_last.log")
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

    def files_window(self):
        win = tk.Toplevel(self)
        win.title("Files, Logs, and Help")
        win.geometry("500x430")
        win.configure(bg=BG)
        tk.Label(win, text="Files, Logs, and Help", bg=BG, fg=TEXT, font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=18, pady=(16, 6))
        tk.Label(win, text="If a button appears to do nothing, open Logs and check the newest *_last.log file.", bg=BG, fg=MUTED, font=("Segoe UI", 10), wraplength=440, justify="left").pack(anchor="w", padx=18, pady=(0, 12))
        items = [
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
    StartCenter().mainloop()


if __name__ == "__main__":
    main()

# v7.1 primary-live note: final package includes cloud_primary_final_check.py for live deployment readiness.
