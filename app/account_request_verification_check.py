# -*- coding: utf-8 -*-
"""Verify account request owner-approval workflow and notifications."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
APP = BASE / "app"
errors: list[str] = []
notes: list[str] = []


def check(name: str, ok: bool, fail: str = "") -> None:
    if ok:
        notes.append(f"OK: {name}")
    else:
        errors.append(fail or name)


def main() -> int:
    ns = (APP / "network_server.py").read_text(encoding="utf-8", errors="ignore")
    an = (APP / "application_notifications.py").read_text(encoding="utf-8", errors="ignore")

    check("approval_required setting", "approval_required" in ns and '"true"' in ns)
    check("account request setting helper", "get_account_request_setting" in ns and "public_account_requests_enabled" in ns)
    check("register reads account_request_settings", "public_account_requests_enabled()" in ns)
    check("public account-request alias route", '"/account-request"' in ns)
    check("login no-account card", "No account yet?" in ns)
    check("connect page public layout", "def connect_links" in ns and 'return layout("Connection Test and Mobile Links", body, "mobile", public=True)' in ns)
    ag = (APP / "auth_gate.py").read_text(encoding="utf-8", errors="ignore")
    check("auth gate register public", "/register" in ag and "/account-request" in ag)
    check("approve requires manage_users", '@login_required("manage_users")' in ns and "approve_account_request" in ns)
    check("admin-only approve guard", "is_admin_role" in ns and "Non-admin attempted account approval" in ns)
    check("admin-only deny guard", "Non-admin attempted account denial" in ns)
    check("register email required", "Email is required so we can notify you" in ns)
    check("owner notify on register", "notify_owner_new_account_request" in ns)
    check("requester notify on approve", "notify_requester_account_decision" in ns)
    check("no manager via self-register approve", "Manager role cannot be granted via public account request" in ns)
    check("notification module account functions", "notify_owner_new_account_request" in an)
    check("owner email default", "enragementwow@hotmail.com" in an or "owner_notification_email" in ns)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO app_settings VALUES ('owner_notification_email', 'enragementwow@hotmail.com');
            CREATE TABLE account_requests (
                id INTEGER PRIMARY KEY, requested_username TEXT, display_name TEXT, email TEXT,
                recovery_email TEXT, phone TEXT, address TEXT, worker_type TEXT, skills TEXT,
                emergency_contact TEXT, preferred_rate REAL, requested_role TEXT, status TEXT,
                request_ip TEXT, created_at TEXT, reviewed_at TEXT, reviewed_by TEXT
            );
            INSERT INTO account_requests (id, requested_username, display_name, email, requested_role, status, created_at)
            VALUES (1, 'testuser', 'Test User', 'test@example.com', 'helper', 'Pending', '2026-06-28');
            """
        )
        conn.commit()
        import os

        os.environ["JRC_LIVE_DIR"] = tmp
        from app.application_notifications import (
            ensure_account_request_notification_columns,
            format_account_request_body,
            notify_owner_new_account_request,
            notify_requester_account_decision,
            requester_email,
        )

        ensure_account_request_notification_columns(conn)
        row = dict(conn.execute("SELECT * FROM account_requests WHERE id=1").fetchone())
        check("requester_email helper", requester_email(row) == "test@example.com")
        body = format_account_request_body(row)
        check("format includes username", "testuser" in body)
        ok1, msg1 = notify_owner_new_account_request(conn, 1, request_base_url="http://127.0.0.1:8765")
        check("owner notify runs", ok1 or "saved" in msg1.lower() or "outbox" in msg1.lower(), msg1)
        ok2, msg2 = notify_requester_account_decision(
            conn, 1, "Approved", "helper", request_base_url="http://127.0.0.1:8765"
        )
        check("requester approve notify runs", ok2 or "saved" in msg2.lower() or "outbox" in msg2.lower(), msg2)
        conn.close()
        outbox = Path(tmp) / "data" / "account_request_email_outbox"
        check("outbox files created", outbox.is_dir() and any(outbox.glob("*.txt")))

    print("JRC Account Request Verification Check")
    print("Errors:", len(errors))
    for e in errors:
        print(" ERROR -", e)
    for n in notes:
        print(" ", n)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
