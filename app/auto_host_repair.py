"""
JRC Auto Host Repair and Log Diagnostics

Purpose:
- Read the local JRC logs automatically.
- Detect common local-host/mobile failures.
- Apply safe repairs that do not delete business data.
- Write a plain-English report in exports.

This tool does not expose the computer to the public internet. It is for local same-Wi-Fi/VPN host repair only.
Remote access from other locations still needs cloud/tunnel/VPN hosting.
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import socket
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR = BASE_DIR / "exports"
REQUIREMENTS = BASE_DIR / "requirements.txt"
LOCAL_HOST_SETTINGS = DATA_DIR / "local_host_settings.json"
CLOUD_CONNECT = DATA_DIR / "cloud_connect.json"
DEFAULT_PORT = int(os.environ.get("JRC_PORT", "8765"))

for folder in [DATA_DIR, LOG_DIR, EXPORT_DIR, BASE_DIR / "backups", BASE_DIR / "evidence", BASE_DIR / "chatgpt_imports"]:
    folder.mkdir(parents=True, exist_ok=True)


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def module_ok(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def read_text(path: Path, limit: int = 12000) -> str:
    try:
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-limit:]
    except Exception as exc:
        return f"<could not read {path}: {exc}>"


def url_check(url: str, timeout: float = 1.4) -> dict:
    started = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(350).decode("utf-8", "ignore")
            return {"url": url, "ok": True, "status": getattr(resp, "status", 200), "seconds": round(time.time() - started, 3), "body": body[:250]}
    except Exception as exc:
        return {"url": url, "ok": False, "seconds": round(time.time() - started, 3), "error": str(exc)}


def socket_open(port: int, host: str = "127.0.0.1", timeout: float = 0.45) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def get_saved_port() -> int:
    try:
        if LOCAL_HOST_SETTINGS.exists():
            return int(json.loads(LOCAL_HOST_SETTINGS.read_text(encoding="utf-8")).get("port", DEFAULT_PORT))
    except Exception:
        pass
    return DEFAULT_PORT


def save_port(port: int, reason: str) -> None:
    payload = {"port": int(port), "updated_at": now(), "reason": reason}
    LOCAL_HOST_SETTINGS.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def port_is_jrc(port: int) -> bool:
    result = url_check(f"http://127.0.0.1:{port}/api/health", timeout=0.7)
    if not result.get("ok"):
        return False
    body = str(result.get("body", "")).lower()
    return "j" in body or "ok" in body or "health" in body


def choose_safe_port(start: int) -> tuple[int, str]:
    # If the saved port is already JRC, keep it. If it is occupied by something else, move.
    if port_is_jrc(start):
        return start, f"Port {start} already answers as a JRC/local health endpoint. Kept it."
    if not socket_open(start):
        return start, f"Port {start} appears free. Kept it."
    for port in range(start + 1, start + 16):
        if port_is_jrc(port):
            return port, f"Port {start} was busy, but port {port} already answers as JRC. Switched setting to {port}."
        if not socket_open(port):
            return port, f"Port {start} was busy with a non-JRC service. Switched setting to free port {port}."
    return start, f"Port {start} is busy and no free nearby port was found. Kept current setting for manual review."


def analyze_logs() -> list[dict]:
    files = [
        LOG_DIR / "shared_host_last.log",
        LOG_DIR / "host_quick_test_last.log",
        LOG_DIR / "auto_host_repair_last.log",
        LOG_DIR / "dependency_repair_last.log",
        LOG_DIR / "system_check_last.log",
        LOG_DIR / "desktop_app_last.log",
    ]
    patterns = [
        (r"ModuleNotFoundError|No module named '?(app|flask|waitress|reportlab)'?", "missing_dependency", "A required package or app module path is wrong. Run Admin → Full Auto-Repair or Background Troubleshooter to fix -m app.* launchers and install dependencies."),
        (r"Address already in use|Only one usage of each socket address", "port_in_use", "The local host port is already in use. Auto repair can switch to a nearby free port."),
        (r"PermissionError|Access is denied", "permission_error", "Windows permissions blocked an action. Try running the Start Center normally, then use Allow Phone Access as admin if needed."),
        (r"Connection refused|timed out|No connection could be made", "connection_failed", "The host was not reachable during the test. It may not have started, or the port/firewall is blocking it."),
        (r"database is locked|sqlite3\.OperationalError", "database_issue", "The database may be busy or locked by another process. Close extra JRC windows and retry."),
        (r"can't open file|No such file or directory", "missing_file", "A required file path was missing. Reinstall/update from the latest ZIP if this persists."),
    ]
    findings = []
    for path in files:
        text = read_text(path)
        if not text:
            continue
        for pat, code, advice in patterns:
            if re.search(pat, text, re.I):
                findings.append({"log": str(path), "code": code, "advice": advice})
    return findings


def main() -> int:
    started = now()
    report: dict = {
        "program": "J & R Construction Manager",
        "tool": "Auto Host Repair and Log Diagnostics",
        "started_at": started,
        "base_dir": str(BASE_DIR),
        "computer": platform.node(),
        "platform": platform.platform(),
        "actions": [],
        "warnings": [],
        "errors": [],
    }

    # Ensure support files/folders exist.
    for folder in [DATA_DIR, LOG_DIR, EXPORT_DIR, BASE_DIR / "backups", BASE_DIR / "evidence", BASE_DIR / "chatgpt_imports"]:
        folder.mkdir(parents=True, exist_ok=True)
        report["actions"].append(f"Verified folder: {folder}")

    try:
        from app.launcher_repair import repair_launcher_files, verify_app_imports
        for action in repair_launcher_files(BASE_DIR):
            report["actions"].append(action)
        ok, msg = verify_app_imports(BASE_DIR)
        if not ok:
            report["warnings"].append(f"Module import check: {msg}")
        else:
            report["actions"].append(msg)
    except Exception as exc:
        report["warnings"].append(f"Launcher repair skipped: {exc}")

    if not CLOUD_CONNECT.exists():
        CLOUD_CONNECT.write_text(json.dumps({"cloud_base_url": "", "updated_at": now(), "note": "Optional remote/cloud URL for JRC Manager."}, indent=2), encoding="utf-8")
        report["actions"].append("Created default cloud_connect.json placeholder.")

    # Dependency scan.
    deps = {name: module_ok(name) for name in ["flask", "waitress", "reportlab"]}
    report["dependency_status"] = deps
    for name, ok in deps.items():
        if not ok:
            report["warnings"].append(f"Missing optional dependency: {name}. Network/mobile/PDF features may not run until Repair Features installs requirements.")

    # Required files.
    required = [APP_DIR / "network_server.py", APP_DIR / "start_center.py", APP_DIR / "system_check.py", APP_DIR / "host_quick_test.py", REQUIREMENTS]
    for path in required:
        if not path.exists():
            report["errors"].append(f"Missing required file: {path}")
        else:
            report["actions"].append(f"Found required file: {path.name}")

    # Port selection / repair.
    saved_port = get_saved_port()
    selected_port, reason = choose_safe_port(saved_port)
    save_port(selected_port, reason)
    report["port_before"] = saved_port
    report["port_after"] = selected_port
    report["actions"].append(reason)

    # Endpoint check on selected port. This does not start the host; it tells if something is answering now.
    base = f"http://127.0.0.1:{selected_port}"
    endpoints = [base + "/api/health", base + "/mobile/ping", base + "/api/connection", base + "/connect"]
    report["endpoint_checks"] = [url_check(url) for url in endpoints]
    if not any(item.get("ok") for item in report["endpoint_checks"]):
        report["warnings"].append("No local host endpoint answered right now. This is normal if the host is not started. Click Start Local Host after this repair finishes.")

    # Log analysis.
    report["log_findings"] = analyze_logs()
    if report["log_findings"]:
        report["warnings"].append("Auto repair found useful clues in the logs. Review log_findings in the JSON report or the text summary.")

    # Windows firewall helper status.
    firewall_helper = BASE_DIR / "ALLOW_LAN_FIREWALL_ACCESS.bat"
    report["firewall_helper_present"] = firewall_helper.exists()
    if firewall_helper.exists():
        report["actions"].append("Firewall helper is present. Run Tools / Repair > Allow Phone Access if phones cannot connect on same Wi-Fi.")
    else:
        report["warnings"].append("Firewall helper is missing. Reinstall/update if phone access fails on same Wi-Fi.")

    # Save reports.
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    json_path = EXPORT_DIR / f"JRC_Auto_Host_Repair_Report_{stamp}.json"
    txt_path = EXPORT_DIR / f"JRC_Auto_Host_Repair_Report_{stamp}.txt"
    report["finished_at"] = now()
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "J & R Construction Manager - Auto Host Repair Report",
        f"Started: {started}",
        f"Finished: {report['finished_at']}",
        f"Program folder: {BASE_DIR}",
        "",
        f"Local host port before: {saved_port}",
        f"Local host port after: {selected_port}",
        reason,
        "",
        "Dependency status:",
    ]
    for name, ok in deps.items():
        lines.append(f"- {name}: {'OK' if ok else 'MISSING'}")
    lines += ["", "Warnings:"]
    lines += [f"- {w}" for w in report["warnings"]] or ["- None"]
    lines += ["", "Errors:"]
    lines += [f"- {e}" for e in report["errors"]] or ["- None"]
    lines += ["", "Endpoint checks:"]
    for item in report["endpoint_checks"]:
        lines.append(f"- {'PASS' if item.get('ok') else 'FAIL'} {item.get('url')} {item.get('error', item.get('body', ''))}")
    lines += ["", "Log findings:"]
    for item in report["log_findings"]:
        lines.append(f"- {item['code']} in {item['log']}: {item['advice']}")
    if not report["log_findings"]:
        lines.append("- None")
    lines += ["", "Next best steps:", "1. Open Start Center.", "2. Click Auto Repair Host first.", "3. Click Start Local Host.", "4. If host verifies on laptop but phone fails, run Allow Phone Access.", "5. For remote access outside your Wi-Fi, use Cloud Access instead of local host."]
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    print("Auto Host Repair finished.")
    print("Text report:", txt_path)
    print("JSON report:", json_path)
    print("Selected port:", selected_port)
    if report["errors"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
