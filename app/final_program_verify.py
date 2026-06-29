"""JRC Manager v5.6 final program verifier.
Runs in the installed program folder and writes a plain-English report.
It uses static checks when Flask is unavailable and live Flask test-client checks when available.
"""
from __future__ import annotations
import datetime as dt, json, os, re, sqlite3, sys, traceback, zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
EXPORT_DIR = BASE_DIR / "exports"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "jr_business.db"
EXPORT_DIR.mkdir(exist_ok=True)

REQUIRED_FILES = [
    "app/network_server.py", "app/start_center.py", "app/admin_db_editor.py", "app/system_check.py", "app/permission_view_check.py",
    "app/security_perspective_audit.py", "app/dashboard_role_check.py", "app/access_mode_check.py",
    "app/auto_host_repair.py", "app/host_quick_test.py", "app/cloud_deploy_check.py",
    "app/final_program_verify.py", "cloud_hosting/Dockerfile", "cloud_hosting/docker-compose.yml",
    "cloud_hosting/render.yaml", "cloud_hosting/Procfile", "requirements.txt", "INSTALL_J_AND_R_MANAGER.vbs"
]
REQUIRED_ROUTES = [
    "/login", "/register", "/", "/mobile", "/connect", "/api/health", "/api/connection",
    "/api/cloud/status", "/cloud-status", "/customer", "/customer/request", "/customer/requests",
    "/customers/requests", "/apply", "/applications", "/admin", "/admin/devices", "/admin/database", "/admin/database/accounts", "/owner-recovery",
    "/emergency-access",
]
ROLE_MARKERS = ["admin", "manager", "worker", "viewer", "non_company", "customer"]
FORBIDDEN_CUSTOMER_EXPOSURE = ["manage_payroll", "view_money", "manage_bookkeeping", "manage_files", "manage_devices", "configure_hosting"]

errors: list[str] = []
warnings: list[str] = []
passes: list[str] = []


def rel(p: Path) -> str:
    try: return str(p.relative_to(BASE_DIR))
    except Exception: return str(p)


def ok(msg: str): passes.append(msg)
def warn(msg: str): warnings.append(msg)
def err(msg: str): errors.append(msg)


def check_files():
    for item in REQUIRED_FILES:
        if (BASE_DIR / item).exists(): ok(f"Required file found: {item}")
        else: err(f"Missing required file: {item}")


def check_syntax():
    import py_compile
    for py in sorted(APP_DIR.glob("*.py")):
        try:
            py_compile.compile(str(py), doraise=True)
            ok(f"Python syntax OK: {rel(py)}")
        except Exception as e:
            err(f"Python syntax failed: {rel(py)} -> {e}")


def check_source_security():
    ns = (APP_DIR / "network_server.py").read_text(encoding="utf-8", errors="replace")
    sc = (APP_DIR / "start_center.py").read_text(encoding="utf-8", errors="replace")
    for route in REQUIRED_ROUTES:
        if route in ns: ok(f"Route marker present: {route}")
        else: err(f"Route marker missing from network_server.py: {route}")
    for role in ROLE_MARKERS:
        if f'"{role}"' in ns or f"'{role}'" in ns: ok(f"Role present: {role}")
        else: err(f"Role missing: {role}")
    if '"customer": {"view_dashboard", "mobile_access", "customer_portal"' in ns:
        ok("Customer role is customer-portal limited")
    else:
        warn("Could not statically confirm exact customer permission set; inspect PERMISSIONS table.")
    customer_line = re.search(r'"customer"\s*:\s*\{([^}]+)\}', ns, re.S)
    if customer_line:
        perms = customer_line.group(1)
        leaked = [p for p in FORBIDDEN_CUSTOMER_EXPOSURE if p in perms]
        if leaked: err("Customer role includes internal permissions: " + ", ".join(leaked))
        else: ok("Customer role does not include internal money/payroll/admin/file management permissions")
    for marker in ["Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"]:
        if marker in ns: ok(f"Security header present: {marker}")
        else: err(f"Missing security header marker: {marker}")
    for marker in ["HttpOnly", "SameSite", "DEVICE_COOKIE_NAME", "JRC_SECRET_KEY", "PUBLIC_HOST_MODE"]:
        if marker in ns: ok(f"Cookie/cloud security marker present: {marker}")
        else: err(f"Missing cookie/cloud security marker: {marker}")
    for marker in ["Final Program Verify", "Cloud Deploy Check", "Host Monitor", "Open Login"]:
        if marker in sc: ok(f"Start Center tool present: {marker}")
        else: err(f"Start Center missing tool: {marker}")


def check_cloud_files():
    dockerfile = BASE_DIR / "cloud_hosting" / "Dockerfile"
    compose = BASE_DIR / "cloud_hosting" / "docker-compose.yml"
    render = BASE_DIR / "cloud_hosting" / "render.yaml"
    entry = BASE_DIR / "cloud_hosting" / "cloud_entry.py"
    for path in [dockerfile, compose, render, entry]:
        if path.exists(): ok(f"Cloud file found: {rel(path)}")
        else: err(f"Cloud file missing: {rel(path)}")
    if dockerfile.exists() and "gunicorn" in dockerfile.read_text(errors="replace"):
        ok("Dockerfile uses gunicorn production server")
    else: warn("Dockerfile gunicorn marker not found")
    if compose.exists() and "volumes:" in compose.read_text(errors="replace"):
        ok("Docker Compose includes persistent volume mappings")
    else: warn("Docker Compose persistent volume marker not found")


def check_database():
    if not DB_PATH.exists():
        warn("Installed database not found in this clean/package environment. System Check will create/repair it on the user's PC.")
        return
    required_tables = ["users", "customers", "jobs", "customer_user_profiles", "customer_job_requests", "account_requests", "online_sessions", "known_devices", "worker_payments", "bookkeeping_ledgers"]
    try:
        conn = sqlite3.connect(DB_PATH)
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in required_tables:
            if t in names: ok(f"Database table present: {t}")
            else: err(f"Database table missing: {t}")
        conn.close()
    except Exception as e:
        err(f"Database check failed: {e}")


def live_flask_checks():
    try:
        sys.path.insert(0, str(BASE_DIR))
        from app import network_server as ns  # type: ignore
        ns.init_db()
        client = ns.app.test_client()
        endpoints = ["/api/health", "/api/connection", "/api/cloud/status", "/connect", "/login", "/register", "/apply"]
        for ep in endpoints:
            r = client.get(ep)
            if r.status_code in (200, 302): ok(f"Live route responded {r.status_code}: {ep}")
            else: err(f"Live route unexpected status {r.status_code}: {ep}")
    except Exception as e:
        warn("Live Flask test-client checks skipped or failed in this environment: " + str(e))


def write_report():
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    txt = EXPORT_DIR / f"JRC_Final_Program_Verification_Report_{ts}.txt"
    js = EXPORT_DIR / f"JRC_Final_Program_Verification_Report_{ts}.json"
    lines = []
    lines.append("J & R Construction Manager - Final Program Verification")
    lines.append(f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Program folder: {BASE_DIR}")
    lines.append("")
    lines.append(f"RESULT: {len(errors)} errors, {len(warnings)} warnings, {len(passes)} passes")
    lines.append("")
    if errors:
        lines.append("ERRORS")
        lines += ["- " + x for x in errors]
        lines.append("")
    if warnings:
        lines.append("WARNINGS")
        lines += ["- " + x for x in warnings]
        lines.append("")
    lines.append("PASSES")
    lines += ["- " + x for x in passes]
    txt.write_text("\n".join(lines), encoding="utf-8")
    js.write_text(json.dumps({"errors":errors,"warnings":warnings,"passes":passes,"generated_at":dt.datetime.now().isoformat()}, indent=2), encoding="utf-8")
    print("Final Program Verification complete")
    print(f"Errors: {len(errors)} Warnings: {len(warnings)} Passes: {len(passes)}")
    print(f"Report: {txt}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    check_files(); check_syntax(); check_source_security(); check_cloud_files(); check_database(); live_flask_checks(); write_report()
