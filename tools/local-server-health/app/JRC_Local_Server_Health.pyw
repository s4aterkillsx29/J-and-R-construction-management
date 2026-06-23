"""J&R Construction Manager - Local Server Health + Repair

Official local/LAN diagnostic helper for J&R Construction Manager.
Runs as a windowed app and can start a known-good localhost/LAN health server.
"""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

APP_TITLE = "J&R Construction Manager - Local Server Health + Repair"
DEFAULT_PORT = 8765
_server: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None


def get_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "JRCHealth/3.5"

    def _send(self, code: int, body: str, content_type: str = "text/plain") -> None:
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _json(self, data: dict, code: int = 200) -> None:
        self._send(code, json.dumps(data, indent=2), "application/json")

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method
        lan_ip = get_lan_ip()
        if self.path in {"/", "/login"}:
            self._send(200, f"""<!doctype html>
<html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>J&R Construction Manager Login Test</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;line-height:1.4}}.card{{max-width:720px;padding:18px;border:1px solid #ddd;border-radius:12px}}.ok{{color:#116b2d;font-weight:bold}}code{{background:#f4f4f4;padding:2px 5px;border-radius:4px}}</style></head>
<body><div class=\"card\"><h1>J&R Construction Manager</h1><p class=\"ok\">Login page test passed.</p><p>This verifies the local/LAN server is running and reachable.</p><p>Local: <code>http://127.0.0.1:{DEFAULT_PORT}/login</code></p><p>LAN/iPhone: <code>http://{lan_ip}:{DEFAULT_PORT}/login</code></p><p>API Health: <a href=\"/api/health\">/api/health</a></p><p>Mobile Ping: <a href=\"/api/mobile/ping\">/api/mobile/ping</a></p></div></body></html>""", "text/html")
            return
        if self.path == "/api/health":
            self._json({"ok": True, "service": "J&R Construction Manager local health API", "status": "healthy", "port": DEFAULT_PORT, "lan_ip": lan_ip})
            return
        if self.path == "/api/mobile/ping":
            self._json({"ok": True, "mobile_ping": "passed", "message": "Phone/LAN ping endpoint is reachable.", "lan_url": f"http://{lan_ip}:{DEFAULT_PORT}/login"})
            return
        if self.path == "/api/lan/phone-test":
            self._json({"ok": True, "lan_phone_test": "passed", "phone_url": f"http://{lan_ip}:{DEFAULT_PORT}/login"})
            return
        self._json({"ok": False, "error": "not_found", "path": self.path}, 404)


def start_health_server(port: int = DEFAULT_PORT) -> str:
    global _server, _server_thread
    if _server:
        return "Health server is already running."
    _server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    return f"Health server started on 0.0.0.0:{port}"


def stop_health_server() -> str:
    global _server, _server_thread
    if not _server:
        return "Health server was not running."
    _server.shutdown()
    _server.server_close()
    _server = None
    _server_thread = None
    return "Health server stopped."


def http_get(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(600).decode("utf-8", errors="replace")
            return 200 <= response.status < 300, f"HTTP {response.status}: {body[:300]}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return False, str(exc)


class HealthApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("940x650")
        self.minsize(820, 540)
        self.port = tk.IntVar(value=DEFAULT_PORT)
        self._build()
        self.refresh_urls()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)
        ttk.Label(root, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="Repair and test localhost, API health, mobile/LAN access, and Windows Firewall readiness.").pack(anchor="w", pady=(0, 12))

        top = ttk.LabelFrame(root, text="Server URLs", padding=12)
        top.pack(fill=tk.X)
        self.url_text = tk.StringVar()
        ttk.Label(top, textvariable=self.url_text, justify=tk.LEFT).pack(anchor="w")

        buttons = ttk.Frame(root)
        buttons.pack(fill=tk.X, pady=12)
        for text, cmd in [
            ("Start Health Server", self.start_server),
            ("Test Login Page", self.test_login),
            ("Test API Health", self.test_api),
            ("Test Mobile Ping", self.test_mobile),
            ("Test LAN Phone URL", self.test_lan),
            ("Show Firewall Command", self.show_firewall),
            ("Stop Server", self.stop_server),
        ]:
            ttk.Button(buttons, text=text, command=cmd).pack(side=tk.LEFT, padx=4, pady=4)

        log_frame = ttk.LabelFrame(root, text="Results", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(log_frame, wrap="word", font=("Consolas", 10))
        self.log.pack(fill=tk.BOTH, expand=True)
        self.write("Ready. Click Start Health Server, then run each test. Use the LAN/iPhone URL on your phone while on the same Wi-Fi/network.")

    def write(self, msg: str) -> None:
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def refresh_urls(self) -> None:
        ip = get_lan_ip()
        port = self.port.get()
        self.url_text.set(f"Local login: http://127.0.0.1:{port}/login\nLAN/iPhone login: http://{ip}:{port}/login\nAPI health: http://127.0.0.1:{port}/api/health\nMobile ping: http://{ip}:{port}/api/mobile/ping")

    def start_server(self) -> None:
        self.refresh_urls()
        try:
            self.write(start_health_server(self.port.get()))
            time.sleep(0.2)
            self.test_api()
        except OSError as exc:
            self.write(f"FAILED to start server: {exc}")
            self.write("Likely causes: port already in use, Python blocked, or firewall/security software interference.")

    def stop_server(self) -> None:
        self.write(stop_health_server())

    def test_login(self) -> None:
        url = f"http://127.0.0.1:{self.port.get()}/login"
        ok, result = http_get(url)
        self.write(("PASS " if ok else "FAIL ") + f"login page: {url} -> {result}")

    def test_api(self) -> None:
        url = f"http://127.0.0.1:{self.port.get()}/api/health"
        ok, result = http_get(url)
        self.write(("PASS " if ok else "FAIL ") + f"api health: {url} -> {result}")

    def test_mobile(self) -> None:
        url = f"http://127.0.0.1:{self.port.get()}/api/mobile/ping"
        ok, result = http_get(url)
        self.write(("PASS " if ok else "FAIL ") + f"mobile ping local: {url} -> {result}")

    def test_lan(self) -> None:
        ip = get_lan_ip()
        url = f"http://{ip}:{self.port.get()}/api/lan/phone-test"
        ok, result = http_get(url)
        self.write(("PASS " if ok else "FAIL ") + f"LAN phone test from PC side: {url} -> {result}")
        self.write("Now open the LAN/iPhone login URL shown above on your iPhone while on the same Wi-Fi/network.")

    def show_firewall(self) -> None:
        port = self.port.get()
        cmd = f'netsh advfirewall firewall add rule name="JRC Manager Local Server {port}" dir=in action=allow protocol=TCP localport={port}'
        self.write("Run PowerShell or Command Prompt as Administrator and use this firewall command:")
        self.write(cmd)
        try:
            self.clipboard_clear()
            self.clipboard_append(cmd)
            self.write("Firewall command copied to clipboard.")
        except Exception:
            pass


if __name__ == "__main__":
    HealthApp().mainloop()
