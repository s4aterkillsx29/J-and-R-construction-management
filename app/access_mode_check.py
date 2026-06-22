"""
JRC Manager v5.1 Access Mode Check
Checks whether desktop, local-host, cloud-link, and role-perspective access are configured in a way that makes sense.
This test does not require the local host to be running.
"""
from __future__ import annotations
import json, os, time, sqlite3, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "jr_business.db"
CLOUD_CONNECT_PATH = DATA_DIR / "cloud_connect.json"
EXPORT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

ROLES = {
    "admin": ["dashboard", "jobs", "money", "files", "payroll", "admin", "applications", "cloud"],
    "manager": ["dashboard", "jobs", "money", "files", "payroll", "applications"],
    "worker": ["dashboard", "assigned_jobs", "shared_files", "mobile"],
    "viewer": ["dashboard", "read_only_jobs", "shared_files", "mobile"],
    "non_company": ["limited_dashboard", "shared_items", "mobile_shell"],
}

REQUIRED = [
    "app/start_center.py", "app/jr_job_manager.py", "app/network_server.py",
    "app/system_check.py", "app/permission_view_check.py", "app/host_quick_test.py",
    "cloud_hosting/README_CLOUD_HOSTING_JRC.txt", "cloud_hosting/Dockerfile",
    "!!! START INSTALL HERE.vbs", "INSTALL_J_AND_R_MANAGER.vbs"
]

def cloud_url() -> str:
    try:
        data = json.loads(CLOUD_CONNECT_PATH.read_text(encoding="utf-8"))
        return str(data.get("cloud_base_url", "")).strip().rstrip("/")
    except Exception:
        return ""

def main() -> int:
    report = []
    errors = []
    warnings = []
    report.append("JRC Manager v5.1 Access Mode + Perspective Check")
    report.append("Generated: " + time.strftime("%Y-%m-%d %H:%M:%S"))
    report.append("Program folder: " + str(BASE_DIR))
    report.append("")
    report.append("Desktop/local office mode: PASS - Open Office does not require network host.")
    c = cloud_url()
    if c:
        report.append(f"Cloud access URL: SET - {c}")
        if not c.startswith("https://"):
            warnings.append("Cloud Access URL is not HTTPS. Secure cookies and remote user login are best with HTTPS.")
    else:
        warnings.append("No Cloud Access URL saved. Remote users cannot connect when this PC host is off until a cloud/tunnel/VPN host URL is configured.")
        report.append("Cloud access URL: NOT SET")
    for rel in REQUIRED:
        if not (BASE_DIR / rel).exists():
            errors.append("Missing required file: " + rel)
    report.append("")
    report.append("Role/Perspective Expected Access:")
    for role, items in ROLES.items():
        report.append(f"- {role}: " + ", ".join(items))
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            integrity = cur.fetchone()[0]
            if integrity != "ok":
                errors.append("Database integrity check failed: " + str(integrity))
            else:
                report.append("")
                report.append("Database integrity: PASS")
            for table in ["users", "online_sessions", "account_requests", "job_applications", "known_devices"]:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                if not cur.fetchone():
                    warnings.append("Database table not found until System Check repairs/creates it: " + table)
            conn.close()
        except Exception as exc:
            warnings.append("Could not inspect database yet: " + str(exc))
    else:
        warnings.append("Database not found yet. Run System Check after first install/open.")
    report.append("")
    report.append("Warnings:")
    report.extend(["- " + w for w in warnings] or ["- none"])
    report.append("")
    report.append("Errors:")
    report.extend(["- " + e for e in errors] or ["- none"])
    report.append("")
    if errors:
        status = "FAIL"
    elif warnings:
        status = "PASS WITH WARNINGS"
    else:
        status = "PASS"
    report.append("STATUS: " + status)
    out = EXPORT_DIR / ("JRC_Access_Mode_Check_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
    out.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print("\nReport saved:", out)
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
