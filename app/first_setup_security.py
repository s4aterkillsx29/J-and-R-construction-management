"""First-time owner setup credentials and password policy."""
from __future__ import annotations

import sqlite3
from typing import Optional, Tuple

DEFAULT_OWNER_USERNAME = "admin"
DEFAULT_OWNER_PASSWORD = "ivygrows"
# Retired first-setup bootstrap account (localhost-only installs before June 2026).
LEGACY_OWNER_USERNAMES = ("ivygrows",)

FORBIDDEN_RESET_PASSWORDS = frozenset({
    "ivygrows",
    "admin",
    "admin123",
    "password",
    "admin/admin",
    "jandr",
    "jrconstruction",
    "jandrconstruction",
    "j&rconstruction",
})


def is_default_first_setup_password(password: str) -> bool:
    return (password or "").strip() == DEFAULT_OWNER_PASSWORD


def is_forbidden_owner_password(password: str) -> bool:
    return (password or "").strip().lower() in FORBIDDEN_RESET_PASSWORDS


def check_password_change_allowed(new_password: str, mastery_key: str = "") -> Tuple[bool, str]:
    """Block restoring first-setup / default passwords unless mastery key is supplied."""
    if not is_forbidden_owner_password(new_password):
        return True, "OK"
    if mastery_key:
        try:
            from app.emergency_access import verify_mastery_key
            if verify_mastery_key(mastery_key):
                return True, "OK"
        except Exception:
            pass
    return (
        False,
        "That password is reserved for first-time owner setup only. "
        "Use your emergency mastery key to restore it, or choose a different password.",
    )


def password_quality_owner(new_password: str, allow_first_setup_default: bool = False) -> Tuple[bool, str]:
    pw = new_password or ""
    if allow_first_setup_default and pw == DEFAULT_OWNER_PASSWORD:
        return True, "OK"
    from app.densus_policy import enforce_densus_password

    return enforce_densus_password(pw, "admin")


def owner_usernames_sql() -> Tuple[str, ...]:
    return (DEFAULT_OWNER_USERNAME,) + LEGACY_OWNER_USERNAMES


def reset_owner_to_first_setup(conn: sqlite3.Connection, mastery_key: str, ip: str = "", user_agent: str = "") -> Tuple[bool, str]:
    """One-time reset of owner account to ivygrows/ivygrows — mastery key required."""
    import hashlib
    import secrets
    from datetime import datetime

    from app.emergency_access import verify_mastery_key

    if not verify_mastery_key(mastery_key):
        return False, "Invalid mastery key. Owner first-setup reset denied."

    OWNER = "Jacob Cosentino"

    def _hash(password: str) -> Tuple[str, str]:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 250000).hex()
        return salt, digest

    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    salt, ph = _hash(DEFAULT_OWNER_PASSWORD)
    row = conn.execute(
        "SELECT id FROM users WHERE username=? LIMIT 1", (DEFAULT_OWNER_USERNAME,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET salt=?, password_hash=?, role='admin', active=1, must_change_password=1, "
            "owner_account=1, access_locked=0, lock_reason=NULL, locked_payment_request_id=NULL WHERE username=?",
            (salt, ph, DEFAULT_OWNER_USERNAME),
        )
    else:
        conn.execute(
            "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, "
            "created_at, notes, email, recovery_email, phone, title, owner_account) "
            "VALUES (?,?,?,?,?,1,1,?,?,?,?,?,?,1)",
            (
                DEFAULT_OWNER_USERNAME,
                OWNER,
                "admin",
                salt,
                ph,
                _now(),
                "Owner first-setup account reset via mastery key.",
                "enragementwow@hotmail.com",
                "enragementwow@hotmail.com",
                "(910) 712-0936",
                "Owner / Administrator",
            ),
        )
    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("owner_setup_complete", "0"))
    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("admin_default_password_changed", "0"))
    conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", ("first_setup_reset_at", _now()))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS owner_recovery_events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, action TEXT, username TEXT, "
        "ip_address TEXT, user_agent TEXT, trusted_admin_device_id TEXT, result TEXT, notes TEXT)"
    )
    conn.execute(
        "INSERT INTO owner_recovery_events (event_time, action, username, ip_address, user_agent, "
        "trusted_admin_device_id, result, notes) VALUES (?,?,?,?,?,?,?,?)",
        (
            _now(),
            "first_setup_owner_reset",
            DEFAULT_OWNER_USERNAME,
            ip,
            user_agent,
            "",
            "OK",
            "Owner account reset to first-time ivygrows setup via mastery key",
        ),
    )
    conn.commit()
    return True, f"Owner account reset to {DEFAULT_OWNER_USERNAME} / first-setup password. Change it after login."
