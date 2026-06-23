"""
JRC host quick test - reliable local/mobile endpoint verification.

This version reads the saved runtime port, scans the fallback range, and reports
whether the currently running host has the required endpoint set. It no longer
assumes only port 8765, which caused false failures when JRC correctly fell back
to 8766, 8767, etc.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
DATA_DIR = BASE_DIR / "data"
LOCAL_HOST_SETTINGS_PATH = DATA_DIR / "local_host_settings.json"
EXPORT_DIR.mkdir(exist_ok=True)

DEFAULT_PORT = int(os.environ.get("JRC_PORT", "8765"))
FALLBACK_PORT_COUNT = int(os.environ.get("JRC_FALLBACK_PORT_COUNT", "15"))
REQUIRED_ENDPOINTS = [
    "/api/health",
    "/mobile/ping",
    "/api/connection",
    "/connect",
    "/mobile",
]


def saved_port() -> int:
    try:
        if LOCAL_HOST_SETTINGS_PATH.exists():
            data = json.loads(LOCAL_HOST_SETTINGS_PATH.read_text(encoding="utf-8"))
            return int(data.get("port", DEFAULT_PORT))
    except Exception:
        pass
    return DEFAULT_PORT


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


def check(url: str, timeout: float = 2.0) -> dict[str, object]:
    started = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(600).decode("utf-8", "ignore")
            return {
                "url": url,
                "ok": True,
                "status": getattr(r, "status", "ok"),
                "seconds": round(time.time() - started, 3),
                "body": body[:400],
            }
    except Exception as exc:
        return {"url": url, "ok": False, "seconds": round(time.time() - started, 3), "error": str(exc)}


def test_port(port: int) -> dict[str, object]:
    local = f"http://127.0.0.1:{int(port)}"
    results = [check(local + path) for path in REQUIRED_ENDPOINTS]
    passed = sum(1 for r in results if r["ok"])
    return {
        "port": int(port),
        "local_base": local,
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
        "results": results,
    }


def choose_ports() -> list[int]:
    first = saved_port()
    ports = [first]
    for port in range(DEFAULT_PORT, DEFAULT_PORT + FALLBACK_PORT_COUNT):
        if port not in ports:
            ports.append(port)
    return ports


def main() -> int:
    lan = lan_ip()
    all_port_results = [test_port(port) for port in choose_ports()]
    best = max(all_port_results, key=lambda row: int(row["passed"]))
    ok = int(best["failed"]) == 0
    port = int(best["port"])
    local = f"http://127.0.0.1:{port}"
    lan_base = f"http://{lan}:{port}"

    report = {
        "program": "J and R Construction Manager",
        "test": "Host Quick Test",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "selected_port": port,
        "saved_port": saved_port(),
        "default_port": DEFAULT_PORT,
        "local_base": local,
        "lan_base": lan_base,
        "summary": {"ok": ok, "passed": int(best["passed"]), "failed": int(best["failed"]), "total": int(best["total"])},
        "selected_port_results": best["results"],
        "all_scanned_ports": all_port_results,
        "mobile_links": {
            "connection_test": lan_base + "/connect",
            "mobile_app": lan_base + "/mobile",
            "worker_signup": lan_base + "/register",
            "job_application": lan_base + "/apply",
        },
        "meaning_if_failed": "If health passes but mobile/connection endpoints fail, an older partial server is probably still running or the app crashed before route registration. Restart Start Center or use Auto Host Repair.",
    }
    out = EXPORT_DIR / f"JRC_Host_Quick_Test_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("JRC Host Quick Test")
    print("Selected local:", local)
    print("Selected LAN:", lan_base)
    print("Saved port:", saved_port(), "Default port:", DEFAULT_PORT)
    for r in best["results"]:
        print(("PASS" if r["ok"] else "FAIL"), r["url"], str(r.get("error", r.get("body", "")))[:180])
    if not ok:
        print("\nScanned ports summary:")
        for row in all_port_results:
            print(f"Port {row['port']}: {row['passed']}/{row['total']} endpoints passed")
    print("Report:", out)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
