"""
JRC host quick test - lightweight endpoint verification for local/mobile server.
Run after starting Shared Host. Saves a report in exports and prints results.
"""
from __future__ import annotations
import json, os, socket, sys, time, urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)
PORT = int(os.environ.get("JRC_PORT", "8765"))

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
    return "127.0.0.1"

def check(url: str, timeout: float = 2.0):
    started = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(400).decode("utf-8", "ignore")
            return {"url": url, "ok": True, "status": getattr(r, "status", "ok"), "seconds": round(time.time()-started, 3), "body": body[:250]}
    except Exception as exc:
        return {"url": url, "ok": False, "seconds": round(time.time()-started, 3), "error": str(exc)}

def main() -> int:
    local = f"http://127.0.0.1:{PORT}"
    lan = f"http://{lan_ip()}:{PORT}"
    endpoints = [
        local + "/api/health",
        local + "/mobile/ping",
        local + "/api/connection",
        local + "/connect",
        local + "/mobile",
        local + "/chat",
        local + "/api/chat/sessions",
    ]
    results = [check(u) for u in endpoints]
    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed
    report = {
        "program": "J and R Construction Manager",
        "test": "Host Quick Test",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "local_base": local,
        "lan_base": lan,
        "summary": {"passed": passed, "failed": failed, "total": len(results)},
        "results": results,
        "mobile_links": {
            "connection_test": lan + "/connect",
            "mobile_app": lan + "/mobile",
            "worker_signup": lan + "/register",
            "job_application": lan + "/apply",
        },
    }
    out = EXPORT_DIR / f"JRC_Host_Quick_Test_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("JRC Host Quick Test")
    print("Local:", local)
    print("LAN:", lan)
    for r in results:
        print(("PASS" if r["ok"] else "FAIL"), r["url"], r.get("error", r.get("body", ""))[:160])
    print("Report:", out)
    return 0 if failed == 0 else 2

if __name__ == "__main__":
    raise SystemExit(main())
