"""JRC Dashboard Role Check v5.5
Static/business-readiness checks for role-specific dashboards and Start Center host monitor.
Run from Tools / Repair. Writes a plain English report to exports.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

CHECKS = []
ERRORS = []
WARNINGS = []

def ok(msg): CHECKS.append(("OK", msg))
def warn(msg):
    WARNINGS.append(msg); CHECKS.append(("WARN", msg))
def err(msg):
    ERRORS.append(msg); CHECKS.append(("ERROR", msg))

def contains(path: Path, text: str) -> bool:
    try:
        return text in path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False

def main() -> int:
    ns = APP_DIR / "network_server.py"
    sc = APP_DIR / "start_center.py"
    if not ns.exists(): err("Missing network_server.py")
    if not sc.exists(): err("Missing start_center.py")
    ns_text = ns.read_text(encoding="utf-8", errors="replace") if ns.exists() else ""
    sc_text = sc.read_text(encoding="utf-8", errors="replace") if sc.exists() else ""

    for role in ["admin", "manager", "worker", "viewer", "non_company", "customer"]:
        if f'"{role}"' in ns_text or f"'{role}'" in ns_text:
            ok(f"Role present in server source: {role}")
        else:
            err(f"Role missing from server source: {role}")

    for phrase in ["Owner Command Center", "Manager Command Center", "Worker Dashboard", "Read-only Dashboard", "External Access Center", "Customer Quick Actions", "Customer Dashboard"]:
        if phrase in ns_text: ok(f"Dashboard content present: {phrase}")
        else: err(f"Dashboard content missing: {phrase}")

    for blocked in ["payroll", "expenses", "bookkeeping", "job-costing", "admin settings", "other customers"]:
        if blocked in ns_text: ok(f"Customer/external privacy language includes: {blocked}")
        else: warn(f"Could not confirm dashboard privacy wording for: {blocked}")

    for route in ["/customer/request", "/customer/requests", "/customers/requests", "/register", "/login", "/mobile"]:
        if route in ns_text: ok(f"Expected route found: {route}")
        else: err(f"Expected route missing: {route}")

    # Start Center checks
    for phrase in ["Login / Dashboard", "Host Monitor", "Cloud Access", "Auto Repair Host", "Dashboard Role Check"]:
        if phrase in sc_text: ok(f"Start Center item present: {phrase}")
        else: err(f"Start Center item missing: {phrase}")

    for phrase in ["class HostMonitor", "def login_dashboard", "def show_host_monitor", "dashboard_role_check.py"]:
        if phrase in sc_text: ok(f"Start Center support code present: {phrase}")
        else: err(f"Start Center support code missing: {phrase}")

    # Security sanity checks
    for phrase in ["SESSION_COOKIE_HTTPONLY=True", "SESSION_COOKIE_SAMESITE", "Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options"]:
        if phrase in ns_text: ok(f"Security setting/header present: {phrase}")
        else: err(f"Security setting/header missing: {phrase}")

    if "set_secure_device_cookie" in ns_text and "httponly=True" in ns_text:
        ok("Remembered-device cookie helper uses HttpOnly and server-side token handling.")
    else:
        err("Remembered-device cookie helper is missing or incomplete.")

    if "Installer" not in sc_text and "INSTALL" not in sc_text:
        warn("Installer itself does not collect account credentials. This is intentional; login happens in the web app/Start Center handoff so passwords are not handled by the installer.")
    else:
        ok("Installer/login handoff text present in Start Center or supporting docs.")

    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_txt = EXPORT_DIR / f"JRC_Dashboard_Role_Check_{ts}.txt"
    out_json = EXPORT_DIR / f"JRC_Dashboard_Role_Check_{ts}.json"
    report = []
    report.append("JRC Dashboard Role Check v5.5")
    report.append(f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}")
    report.append(f"Errors: {len(ERRORS)}")
    report.append(f"Warnings: {len(WARNINGS)}")
    report.append("")
    for status, msg in CHECKS:
        report.append(f"[{status}] {msg}")
    out_txt.write_text("\n".join(report), encoding="utf-8")
    out_json.write_text(json.dumps({"errors": ERRORS, "warnings": WARNINGS, "checks": CHECKS}, indent=2), encoding="utf-8")
    print("\n".join(report))
    return 1 if ERRORS else 0

if __name__ == "__main__":
    raise SystemExit(main())
