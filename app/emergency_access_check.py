"""Emergency admin access + full install/account-type verification."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

REPORT: list[str] = []
ERRORS: list[str] = []
WARNINGS: list[str] = []


def line(text: str) -> None:
    REPORT.append(text)


def ok(text: str) -> None:
    line(f"OK - {text}")


def warn(text: str) -> None:
    WARNINGS.append(text)
    line(f"WARNING - {text}")


def err(text: str) -> None:
    ERRORS.append(text)
    line(f"ERROR - {text}")


def check_emergency_setup(install_dir: Path) -> None:
    from app.emergency_access import (
        DEFAULT_MASTERY_PASSWORD,
        ensure_mastery_key_on_owner_install,
        grant_emergency_admin_access,
        verify_emergency_access_setup,
        verify_mastery_key,
    )
    from app.install_setup_log import log_event

    os.environ["JRC_DATA_DIR"] = str(install_dir / "data")
    seeded, seed_msg = ensure_mastery_key_on_owner_install(install_dir)
    if seeded:
        ok(f"Owner mastery key: {seed_msg}")
        log_event(install_dir, "EmergencyAccess", seed_msg, level="INFO", step="emergency_access")
    else:
        ok(f"Worker/client skip: {seed_msg}")

    result = verify_emergency_access_setup(install_dir)
    for check in result.get("checks", []):
        name = check.get("name", "check")
        if check.get("status") == "PASS":
            ok(name + (f" ({check['detail']})" if check.get("detail") else ""))
        else:
            err(name + (f" ({check['detail']})" if check.get("detail") else ""))

    db_path = install_dir / "data" / "jr_business.db"
    if not db_path.exists() or not verify_mastery_key(DEFAULT_MASTERY_PASSWORD):
        warn("Skipping live grant_emergency_admin_access test — no owner DB or mastery key")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    before = conn.execute(
        "SELECT COUNT(*) AS n FROM owner_recovery_events WHERE action='mastery_key_admin_access'"
    ).fetchone()
    before_n = int(before["n"]) if before else 0
    ok_grant, msg = grant_emergency_admin_access(conn, "127.0.0.1", "emergency_access_check.py")
    after = conn.execute(
        "SELECT COUNT(*) AS n FROM owner_recovery_events WHERE action='mastery_key_admin_access'"
    ).fetchone()
    after_n = int(after["n"]) if after else 0
    if ok_grant and after_n > before_n:
        ok(f"grant_emergency_admin_access logged recovery event: {msg}")
    elif ok_grant:
        err("grant_emergency_admin_access succeeded but owner_recovery_events not incremented")
    else:
        err(f"grant_emergency_admin_access failed: {msg}")
    conn.close()


def check_web_emergency_route() -> None:
    from app import network_server as ns
    from app.emergency_access import DEFAULT_MASTERY_PASSWORD

    ns.init_db()
    client = ns.app.test_client()
    resp = client.get("/emergency-access")
    ok("/emergency-access GET") if resp.status_code == 200 else err(f"/emergency-access GET returned {resp.status_code}")

    bad = client.post("/emergency-access", data={"mastery_key": "not-the-key"}, follow_redirects=False)
    ok("invalid mastery key rejected") if bad.status_code in (302, 303) else err(
        f"invalid mastery POST returned {bad.status_code}"
    )

    good = client.post(
        "/emergency-access",
        data={"mastery_key": DEFAULT_MASTERY_PASSWORD},
        follow_redirects=False,
    )
    if good.status_code in (302, 303):
        ok("valid mastery key grants emergency web access")
        with client.session_transaction() as sess:
            role = sess.get("role")
            if role == "admin":
                ok("emergency web session role normalized to admin")
            else:
                err(f"emergency web session role wrong: {role!r}")
    else:
        err(f"valid mastery POST returned {good.status_code}")


def check_all_account_types() -> None:
    from app import network_server as ns

    def ensure_user(username: str, role: str, password: str = "TestPass123!") -> None:
        with ns.direct_db() as conn:
            row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            salt, ph = ns.hash_password(password)
            if row:
                conn.execute(
                    "UPDATE users SET role=?, active=1, salt=?, password_hash=?, must_change_password=0, display_name=? WHERE username=?",
                    (role, salt, ph, f"QA {role}", username),
                )
            else:
                conn.execute(
                    "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes) VALUES (?,?,?,?,?,1,0,?,?)",
                    (username, f"QA {role}", role, salt, ph, ns.now_iso(), "Created by emergency_access_check.py"),
                )
            conn.commit()

    ns.init_db()
    role_tests = {
        "admin": {"allow": ["/", "/jobs", "/admin"], "deny": []},
        "manager": {"allow": ["/", "/jobs"], "deny": ["/admin/devices"]},
        "worker": {"allow": ["/", "/jobs", "/mobile/jobs"], "deny": ["/admin", "/payroll"]},
        "viewer": {"allow": ["/", "/jobs"], "deny": ["/admin", "/payroll"]},
        "non_company": {"allow": ["/", "/sharing", "/mobile"], "deny": ["/jobs", "/admin"]},
        "customer": {"allow": ["/", "/customer", "/mobile"], "deny": ["/jobs", "/admin", "/bookkeeping"]},
    }
    for role in role_tests:
        ensure_user(f"qa_{role}", role)
    ok("QA users ensured for all account types")

    client = ns.app.test_client()
    for role, tests in role_tests.items():
        with client.session_transaction() as sess:
            sess.clear()
        resp = client.post("/login", data={"username": f"qa_{role}", "password": "TestPass123!"}, follow_redirects=False)
        if resp.status_code not in (302, 303):
            err(f"{role} login failed with {resp.status_code}")
            continue
        ok(f"{role} login OK")
        for path in tests["allow"]:
            r = client.get(path, follow_redirects=False)
            if r.status_code == 200:
                ok(f"{role} allowed {path}")
            else:
                err(f"{role} expected 200 on {path}, got {r.status_code}")
        for path in tests["deny"]:
            r = client.get(path, follow_redirects=False)
            if r.status_code == 403:
                ok(f"{role} denied {path}")
            else:
                err(f"{role} expected 403 on {path}, got {r.status_code}")


def check_install_artifacts(install_dir: Path) -> None:
    required = [
        "app/emergency_access.py",
        "app/emergency_routes.py",
        "app/local_login_gate.py",
        "install_jr_job_manager_ui.ps1",
        "scripts/Seed-OwnerEmergencyKey.ps1",
    ]
    for rel in required:
        path = install_dir / rel
        ok(f"install artifact {rel}") if path.exists() else err(f"missing install artifact {rel}")

    ps1 = (install_dir / "install_jr_job_manager_ui.ps1").read_text(encoding="utf-8", errors="replace")
    if "seed_mastery_key_on_install" in ps1:
        ok("installer seeds owner emergency mastery key")
    else:
        err("installer missing seed_mastery_key_on_install call")

    gate = (install_dir / "app/local_login_gate.py").read_text(encoding="utf-8", errors="replace")
    if "Emergency Owner Access" in gate and "verify_mastery_key" in gate:
        ok("local login gate exposes emergency owner access")
    else:
        err("local login gate missing emergency owner access wiring")


def run(install_dir: Path | None = None) -> int:
    install_dir = Path(
        install_dir
        or os.environ.get("JRC_LIVE_DIR")
        or os.path.expandvars(r"%LOCALAPPDATA%\J_and_R_Construction_Manager")
    ).resolve()
    if not install_dir.exists():
        install_dir = BASE_DIR

    line("J&R Emergency Access + Full Install Account-Type Check")
    line(f"Started: {dt.datetime.now().isoformat(timespec='seconds')}")
    line(f"Install folder: {install_dir}")
    line("")

    os.chdir(str(install_dir))
    os.environ.setdefault("JRC_DATA_DIR", str(install_dir / "data"))

    check_install_artifacts(install_dir if (install_dir / "app").exists() else BASE_DIR)
    check_emergency_setup(install_dir if (install_dir / "data").exists() else BASE_DIR)
    try:
        check_web_emergency_route()
        check_all_account_types()
    except Exception as exc:
        err(f"Flask emergency/account tests failed: {type(exc).__name__}: {exc}")

    line("")
    line(f"Summary: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s)")
    report_path = EXPORT_DIR / f"emergency_access_check_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.write_text("\n".join(REPORT), encoding="utf-8")
    print("\n".join(REPORT))
    print(f"\nReport saved: {report_path}")

    try:
        from app.install_setup_log import log_event, write_setup_report

        log_event(
            install_dir,
            "EmergencyCheck",
            f"Emergency access check finished: {len(ERRORS)} errors, {len(WARNINGS)} warnings",
            level="INFO" if not ERRORS else "ERROR",
            step="emergency_access",
        )
        write_setup_report(install_dir)
    except Exception:
        pass

    return 1 if ERRORS else 0


if __name__ == "__main__":
    arg_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    raise SystemExit(run(arg_dir))
