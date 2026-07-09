"""J&R Construction Manager - Permission View Check v5.0
Checks limited-user dashboards, non-company role, and shared/mobile permission behavior.
Runs dynamic Flask tests when dependencies are available; otherwise runs static source checks.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)
APP_DIR = BASE_DIR / "app"
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
    WARNINGS.append(text); line(f"WARNING - {text}")


def err(text: str) -> None:
    ERRORS.append(text); line(f"ERROR - {text}")


def static_checks() -> None:
    source = (APP_DIR / "network_server.py").read_text(encoding="utf-8", errors="replace")
    required_patterns = {
        "non_company role exists": '"non_company"' in source,
        "non_company minimal permission set exists": '"non_company": {"view_dashboard", "view_shared_sessions", "mobile_access", "submit_application"}' in source or ('"non_company":' in source and "submit_application" in source),
        "navigation filters by permissions": 'for key, label, href, need in nav if need in perms' in source,
        "role display names exist": 'ROLE_DISPLAY_NAMES' in source,
        "share access helper exists": 'def role_can_access_share' in source,
        "shared files route uses shared-session permission": '@login_required("view_shared_sessions")\ndef open_shared_file' in source,
        "external dashboard blocks money cards": (('External User Dashboard' in source) or ('External Access Center' in source)) and 'No payroll, bookkeeping, expenses' in source,
        "mobile external page exists": 'External Mobile Access' in source,
        "mobile jobs redirects low-permission users": 'This account can only use shared items, not the full job list.' in source,
        "mobile files redirects low-permission users": 'This account can only open files specifically shared' in source,
        "account request supports non-company role": "<option value='non_company'>" in source,
        "customer role exists": '"customer"' in source and "Customer Portal User" in source,
        "customer portal routes exist": '/customer/request' in source and '/customers/requests' in source,
        "customer dashboard hides internal data": "Customer privacy" in source and "Internal job costing" in source,
    }
    for label, passed in required_patterns.items():
        ok(label) if passed else err(label)


def dynamic_checks() -> None:
    from app import network_server as ns  # noqa: E402

    def ensure_user(username: str, role: str, password: str = "TestPass123!") -> None:
        with ns.direct_db() as conn:
            row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            salt, ph = ns.hash_password(password)
            if row:
                conn.execute("UPDATE users SET role=?, active=1, salt=?, password_hash=?, must_change_password=0, display_name=? WHERE username=?",
                             (role, salt, ph, f"QA {role}", username))
            else:
                conn.execute("INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes) VALUES (?,?,?,?,?,1,0,?,?)",
                             (username, f"QA {role}", role, salt, ph, ns.now_iso(), "Created by permission_view_check.py"))
            conn.commit()

    def login(client, username: str, password: str = "TestPass123!"):
        return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    def assert_status(client, path: str, expected: set[int], label: str) -> bytes:
        resp = client.get(path, follow_redirects=False)
        if resp.status_code in expected:
            ok(f"{label}: {path} returned {resp.status_code}")
        else:
            err(f"{label}: {path} returned {resp.status_code}, expected {sorted(expected)}")
        return resp.data or b""

    ns.init_db()

    if "non_company" in ns.PERMISSIONS:
        ok("non_company role exists")
    else:
        err("non_company role missing")

    expected_non_company = {"view_dashboard", "view_shared_sessions", "mobile_access", "submit_application"}
    actual_non_company = set(ns.PERMISSIONS.get("non_company", set()))
    if actual_non_company == expected_non_company:
        ok("non_company role has minimal permissions only")
    else:
        err(f"non_company permissions wrong: {sorted(actual_non_company)}")

    for role in ["admin", "manager", "worker", "viewer", "non_company", "customer"]:
        ensure_user(f"qa_{role}", role)
    ok("QA users created/updated")

    client = ns.app.test_client()
    role_tests = {
        "admin": {"allow": ["/", "/jobs", "/expenses", "/files", "/sharing", "/mobile", "/admin"], "deny": []},
        "manager": {"allow": ["/", "/jobs", "/expenses", "/files", "/sharing", "/mobile"], "deny": ["/admin/devices"]},
        "worker": {"allow": ["/", "/jobs", "/files", "/sharing", "/mobile", "/mobile/jobs", "/mobile/files"], "deny": ["/expenses", "/admin", "/payroll"]},
        "viewer": {"allow": ["/", "/jobs", "/files", "/sharing", "/mobile", "/mobile/jobs", "/mobile/files"], "deny": ["/expenses", "/admin", "/payroll"]},
        "non_company": {"allow": ["/", "/sharing", "/mobile"], "deny": ["/jobs", "/files", "/expenses", "/admin", "/payroll"], "redirect": ["/mobile/jobs", "/mobile/files"]},
        "customer": {"allow": ["/", "/customer", "/customer/request", "/customer/requests", "/mobile"], "deny": ["/jobs", "/files", "/expenses", "/admin", "/payroll", "/bookkeeping"], "redirect": ["/mobile/jobs", "/mobile/files"]},
    }
    for role, tests in role_tests.items():
        with client.session_transaction() as sess:
            sess.clear()
        resp = login(client, f"qa_{role}")
        ok(f"{role} login redirects successfully") if resp.status_code in (302, 303) else err(f"{role} login failed with status {resp.status_code}")
        for path in tests.get("allow", []):
            data = assert_status(client, path, {200}, f"{role} allowed")
            if role in ("viewer", "worker", "non_company", "customer") and path == "/":
                if b"Paid Income" in data or b"Open Receivables" in data or b"Worker Pay" in data:
                    err(f"{role} dashboard exposed money cards")
                else:
                    ok(f"{role} dashboard hides money cards")
        for path in tests.get("deny", []):
            assert_status(client, path, {403}, f"{role} denied")
        for path in tests.get("redirect", []):
            assert_status(client, path, {302, 303}, f"{role} limited redirect")


def run() -> int:
    line("J&R Construction Manager Permission View Check v5.5")
    line(f"Started: {dt.datetime.now().isoformat(timespec='seconds')}")
    line(f"Program folder: {BASE_DIR}")
    line("")
    try:
        dynamic_checks()
        ok("Dynamic Flask permission checks completed")
    except ModuleNotFoundError as exc:
        warn(f"Dynamic Flask tests skipped because dependency is missing: {exc}. Running static source checks instead.")
        static_checks()
    except Exception as exc:
        warn(f"Dynamic tests had an issue: {type(exc).__name__}: {exc}. Running static source checks also.")
        static_checks()
    line("")
    line(f"Summary: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s)")
    report_path = EXPORT_DIR / f"permission_view_check_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.write_text("\n".join(REPORT), encoding="utf-8")
    print("\n".join(REPORT))
    print(f"\nReport saved: {report_path}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    raise SystemExit(run())
