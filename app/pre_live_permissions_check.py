# -*- coding: utf-8 -*-
"""Pre-live security and permissions double-check — run before LAN/public live test."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

EXPORT = BASE / "exports"


def _probe(url: str, *, protected: bool = False) -> tuple[bool, str]:
    """protected=True: must redirect to login or show login page, not expose app data."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=8) as resp:
            code = resp.status
            body = resp.read(8000).decode("utf-8", errors="ignore").lower()
            if protected:
                if code in (401, 403):
                    return True, f"HTTP {code} blocked"
                if "sign in" in body or "login" in body or 'name="username"' in body:
                    return True, f"HTTP {code} login page (gate OK)"
                return False, f"HTTP {code} may expose content without login"
            return True, f"HTTP {code}"
    except urllib.error.HTTPError as exc:
        loc = (exc.headers.get("Location") or "").lower()
        if protected and exc.code in (302, 303, 307, 308) and "login" in loc:
            return True, f"redirect {exc.code} to login"
        if exc.code == 403:
            return True, "403 forbidden"
        if not protected and exc.code in (200, 302):
            return True, f"HTTP {exc.code}"
        return False, f"HTTP {exc.code} loc={loc[:80]}"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    base = Path(os.environ.get("JRC_LIVE_DIR") or BASE).resolve()
    os.environ.setdefault("JRC_DATA_DIR", str(base / "data"))
    port = os.environ.get("JRC_PORT", "8765")
    host = f"http://127.0.0.1:{port}"
    errors: list[str] = []
    notes: list[str] = []

    def ok(name: str, passed: bool, detail: str = "") -> None:
        line = f"{'PASS' if passed else 'FAIL'}: {name}" + (f" — {detail}" if detail else "")
        print(line)
        if passed:
            notes.append(name)
        else:
            errors.append(line)

    print("=" * 62)
    print("J & R CONSTRUCTION MANAGER — PRE-LIVE PERMISSIONS CHECK")
    print(f"Install: {base}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)

    for mod, label in (
        ("app.file_access_security", "file access + role permissions"),
        ("app.account_request_verification_check", "account request approval flow"),
        ("app.ui_dashboard_final_check", "dashboard UI + nav wiring"),
    ):
        try:
            import importlib

            m = importlib.import_module(mod)
            code = m.main() if hasattr(m, "main") else 0
            ok(label, code == 0, f"exit {code}")
        except Exception as exc:
            ok(label, False, str(exc))

    ns = (base / "app" / "network_server.py").read_text(encoding="utf-8", errors="ignore")
    ok("global login gate", "enforce_global_login_required" in ns)
    ok("admin surface protection", "protect_admin_and_sensitive_surfaces" in ns)
    ok("security response headers", "set_security_headers" in ns and "X-Frame-Options" in ns)
    ok("password hashing", "password_hash" in ns and "hash_password" in ns)
    ok("session revoke", "revoke_session" in ns or "revoked" in ns)
    ok("account approval owner-only", "is_admin_role" in ns and "approve_account_request" in ns)

    try:
        from app.auth_gate import PUBLIC_API, is_public_path

        ok("/login public", is_public_path("/login"))
        ok("/admin not public", not is_public_path("/admin"))
        ok("/files not public", not is_public_path("/files"))
        ok("health API public", "/api/health" in PUBLIC_API)
        ok("live ready API public", "/api/live/ready" in PUBLIC_API)
    except Exception as exc:
        ok("auth_gate module", False, str(exc))

    try:
        from app.densus_access import ensure_schema, is_primary_owner
        import sqlite3

        ok("densus owner-approval module", True)
        ok("primary owner constant", is_primary_owner("admin"))
        db_path = base / "data" / "jr_business.db"
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            conn.close()
            ok("densus_access_grants schema", True)
        else:
            ok("densus_access_grants schema", False, "no database yet")
    except Exception as exc:
        ok("densus owner-approval module", False, str(exc))

    try:
        from app.role_permissions import PERMISSIONS

        for role in ("customer", "guest", "helper", "worker"):
            perms = PERMISSIONS.get(role, set())
            ok(f"{role} no view_admin", "view_admin" not in perms)
        ok("admin has view_admin", "view_admin" in PERMISSIONS.get("admin", set()))
        ok("customer shared only", "view_customer_shared" in PERMISSIONS.get("customer", set()))
        ok("customer no view_files", "view_files" not in PERMISSIONS.get("customer", set()))
    except Exception as exc:
        ok("role_permissions", False, str(exc))

    print("\n--- Live HTTP probes (unauthenticated) ---")
    for path in ("/admin", "/files", "/payroll", "/jobs", "/data", "/business"):
        passed, detail = _probe(f"{host}{path}", protected=True)
        ok(f"unauth {path} blocked", passed, detail)

    for path in ("/api/health", "/api/live/ready", "/mobile/ping", "/login", "/register"):
        passed, detail = _probe(f"{host}{path}", protected=False)
        ok(f"public {path}", passed, detail)

    try:
        from app.network_server import is_default_admin_password_active

        default_pw = is_default_admin_password_active()
        if default_pw:
            ok("default admin password changed", False, "CHANGE ivygrows password before sharing LAN access")
        else:
            ok("default admin password changed", True, "owner password no longer default")
    except Exception as exc:
        ok("default admin password check", False, str(exc))

    print("\n" + "=" * 62)
    print(f"SUMMARY: {len(errors)} error(s), {len(notes)} pass(es)")
    if errors:
        print("\nACTION REQUIRED:")
        for e in errors:
            print(f"  * {e}")
    else:
        print("VERDICT: Permissions and security checks PASS — ready for live test.")

    EXPORT.mkdir(exist_ok=True)
    report = EXPORT / f"JRC_Pre_Live_Permissions_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report.write_text(
        json.dumps(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "install": str(base),
                "errors": errors,
                "pass_count": len(notes),
                "ready": len(errors) == 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Report: {report}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
