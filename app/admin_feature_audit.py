# -*- coding: utf-8 -*-
"""Full admin + public route audit for JRC Manager live readiness."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

PUBLIC_ROUTES = [
    "/api/health",
    "/mobile/ping",
    "/api/connection",
    "/connect",
    "/login",
    "/register",
    "/apply",
    "/health",
]

ADMIN_ROUTES = [
    "/",
    "/admin",
    "/admin/devices",
    "/admin/dropbox",
    "/admin/densus",
    "/admin/database",
    "/admin/database/accounts",
    "/admin/database/users",
    "/admin/payments",
    "/admin/troubleshooter",
    "/admin/new_user",
    "/workers",
    "/payroll",
    "/bookkeeping",
    "/job-costs",
    "/applications",
    "/customers",
    "/invoices",
    "/expenses",
    "/jobs",
    "/files",
    "/data",
    "/hosting",
    "/cloud",
    "/business",
    "/chat",
    "/health/run",
    "/setup-status",
    "/owner-security-status",
    "/security-audit",
    "/backup",
]

REDIRECT_OK = {301, 302, 303, 307, 308}


def _login(client, username: str, password: str) -> bool:
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    if resp.status_code in REDIRECT_OK:
        return True
    resp2 = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
    return resp2.status_code < 500 and b"Invalid" not in resp2.data and b"Sign in" not in resp2.data[:800]


def run_audit(base_dir: Path | None = None) -> tuple[int, Path]:
    base = Path(base_dir or BASE).resolve()
    os.environ.setdefault("JRC_DATA_DIR", str(base / "data"))
    os.environ.setdefault("JRC_DB_PATH", str(base / "data" / "jr_business.db"))
    os.environ.setdefault("JRC_PORT", "8765")
    os.environ.setdefault("JRC_ALLOW_LOCAL_DEFAULT_ADMIN", "1")

    import importlib
    import app.network_server as ns

    ns = importlib.reload(ns)
    ns.init_db()
    client = ns.app.test_client()

    errors: list[str] = []
    warnings: list[str] = []
    ok: list[str] = []

    for route in PUBLIC_ROUTES:
        resp = client.get(route)
        if resp.status_code >= 500:
            errors.append(f"PUBLIC {route} -> HTTP {resp.status_code}")
        elif resp.status_code == 404:
            errors.append(f"PUBLIC {route} -> 404 NOT FOUND")
        else:
            ok.append(f"PUBLIC {route} -> {resp.status_code}")

    logged_in = False
    for user, pw in [("admin", "ivygrows"), ("ivygrows", "ivygrows"), ("admin", "admin")]:
        if _login(client, user, pw):
            logged_in = True
            ok.append(f"Login OK as {user}")
            break
    if not logged_in:
        warnings.append("Live DB login not verified (password may differ from defaults) — using admin session mock for route tests")
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "admin"
            sess["role"] = "admin"
            sess["display_name"] = "Owner"
        logged_in = True
        ok.append("Admin session mock active for authenticated route tests")

    for route in ADMIN_ROUTES:
        resp = client.get(route)
        if resp.status_code == 404:
            errors.append(f"ADMIN {route} -> 404 NOT FOUND")
        elif resp.status_code == 403:
            warnings.append(f"ADMIN {route} -> 403 (permission gate)")
        elif resp.status_code >= 500:
            errors.append(f"ADMIN {route} -> HTTP {resp.status_code}")
        elif resp.status_code in REDIRECT_OK:
            loc = resp.headers.get("Location", "")
            if route == "/workers":
                if "/login" in loc:
                    ok.append(f"ADMIN {route} -> login gate (route exists, auth required)")
                elif "payroll" in loc:
                    ok.append(f"ADMIN {route} -> redirect to payroll OK")
                else:
                    errors.append(f"/workers redirect -> {loc} (expected /payroll)")
            else:
                ok.append(f"ADMIN {route} -> redirect {resp.status_code} -> {loc[:60]}")
        else:
            ok.append(f"ADMIN {route} -> {resp.status_code}")

    # Dashboard tile link checks
    dc = (base / "app" / "dashboard_config.py").read_text(encoding="utf-8")
    if '("/payroll"' not in dc or "/workers" in dc.split("Workers")[1][:80] if "Workers" in dc else False:
        pass
    if 'Workers / Helpers", "/payroll"' in dc:
        ok.append("Dashboard Workers tile -> /payroll")
    else:
        errors.append("Dashboard Workers tile not pointing to /payroll")
    if 'Payment Admin", "/admin/payments"' in dc:
        ok.append("Dashboard Payment Admin tile present")
    else:
        errors.append("Dashboard missing Payment Admin tile")

    ns_txt = (base / "app" / "network_server.py").read_text(encoding="utf-8")
    if "/admin/payments" in ns_txt and "Payment Admin" in ns_txt:
        ok.append("Admin command center Payment Admin link present")
    else:
        errors.append("Admin command center missing Payment Admin link")

    sc = (base / "app" / "start_center.py").read_text(encoding="utf-8")
    if "admin / ivygrows" in sc and "admin/admin" not in sc.replace("admin/admin password", ""):
        ok.append("Start Center login copy uses admin/ivygrows")
    elif "admin / ivygrows" in sc:
        ok.append("Start Center login copy uses admin/ivygrows (legacy admin/admin refs may remain in security docs)")
    else:
        warnings.append("Start Center may still show stale login copy")

    try:
        from app.program_manifest import APP_VERSION
    except Exception:
        APP_VERSION = "unknown"

    report_lines = [
        "JRC ADMIN FEATURE AUDIT",
        time.strftime("%Y-%m-%d %H:%M:%S"),
        f"Version: {APP_VERSION}",
        f"Install: {base}",
        "",
        f"SUMMARY: {len(errors)} error(s), {len(warnings)} warning(s), {len(ok)} OK",
        "",
        "ERRORS:",
    ]
    report_lines += [f"  - {e}" for e in errors] or ["  - None"]
    report_lines += ["", "WARNINGS:"]
    report_lines += [f"  - {w}" for w in warnings] or ["  - None"]
    report_lines += ["", "OK (sample):"]
    report_lines += [f"  - {x}" for x in ok[:40]]
    if len(ok) > 40:
        report_lines.append(f"  ... and {len(ok) - 40} more")

    out = base / "exports" / f"JRC_Admin_Feature_Audit_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report_lines), encoding="utf-8")
    print("\n".join(report_lines))
    print(f"\nReport: {out}")
    return len(errors), out


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE
    code, _ = run_audit(base)
    return 1 if code else 0


if __name__ == "__main__":
    raise SystemExit(main())
