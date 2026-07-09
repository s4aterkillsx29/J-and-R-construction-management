"""Ensure built-in test accounts exist for QA and security audits."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from typing import Callable, Tuple

TEST_CUSTOMER_USERNAME = "testcustomer"
TEST_CUSTOMER_PASSWORD = "test"
TEST_CUSTOMER_DISPLAY = "Test Customer"


def _default_hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 250000).hex()
    return salt, digest


def ensure_test_customer(
    conn: sqlite3.Connection,
    *,
    hash_password: Callable[[str, str | None], tuple[str, str]] | None = None,
) -> Tuple[bool, str]:
    """Create or refresh the TestCustomer portal account (testcustomer / test)."""
    hp = hash_password or _default_hash_password
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE LOWER(username)=?",
        (TEST_CUSTOMER_USERNAME.lower(),),
    ).fetchone()
    salt, ph = hp(TEST_CUSTOMER_PASSWORD)
    now_fn = None
    try:
        from app.network_server import now_iso

        now_fn = now_iso
    except Exception:
        import datetime as dt

        now_fn = lambda: dt.datetime.now().isoformat(timespec="seconds")

    ts = now_fn()
    if row:
        conn.execute(
            """UPDATE users SET display_name=?, role='customer', salt=?, password_hash=?,
               active=1, must_change_password=0, notes=? WHERE id=?""",
            (
                TEST_CUSTOMER_DISPLAY,
                salt,
                ph,
                "Built-in QA customer account — portal testing only.",
                row["id"] if hasattr(row, "keys") else row[0],
            ),
        )
        user_id = row["id"] if hasattr(row, "keys") else row[0]
        action = "updated"
    else:
        cur = conn.execute(
            """INSERT INTO users (username, display_name, role, salt, password_hash, active,
               must_change_password, created_at, notes, title)
               VALUES (?, ?, 'customer', ?, ?, 1, 0, ?, ?, 'Customer Portal Test')""",
            (
                TEST_CUSTOMER_USERNAME,
                TEST_CUSTOMER_DISPLAY,
                salt,
                ph,
                ts,
                "Built-in QA customer account — portal testing only.",
            ),
        )
        user_id = cur.lastrowid
        action = "created"

    profile = conn.execute(
        "SELECT id FROM customer_user_profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    if not profile:
        conn.execute(
            """INSERT INTO customer_user_profiles
               (user_id, username, display_name, portal_status, created_at, updated_at, notes)
               VALUES (?, ?, ?, 'Active', ?, ?, ?)""",
            (
                user_id,
                TEST_CUSTOMER_USERNAME,
                TEST_CUSTOMER_DISPLAY,
                ts,
                ts,
                "Auto-created for customer portal QA.",
            ),
        )
    else:
        conn.execute(
            """UPDATE customer_user_profiles SET username=?, display_name=?, portal_status='Active',
               updated_at=? WHERE user_id=?""",
            (TEST_CUSTOMER_USERNAME, TEST_CUSTOMER_DISPLAY, ts, user_id),
        )
    conn.commit()
    return True, f"TestCustomer account {action} (username={TEST_CUSTOMER_USERNAME})."
