"""Shared role normalization for desktop, web, and installer."""
from __future__ import annotations

import sqlite3
from typing import Iterable

DEFAULT_OWNER_USERNAME = "ivygrows"
DEFAULT_OWNER_PASSWORD = "ivygrows"

ROLE_LABELS = ("admin", "manager", "worker", "helper", "subcontractor", "viewer", "guest", "non_company", "customer")

ROLE_DISPLAY = {
    "admin": "Owner/Admin",
    "manager": "Manager",
    "worker": "Company Employee",
    "helper": "Field Helper",
    "subcontractor": "Subcontractor (1099)",
    "viewer": "Read-only Viewer",
    "guest": "Guest / Applicant",
    "non_company": "External User",
    "customer": "Customer Portal",
}

UI_ROLE_CHOICES = ("admin", "manager", "worker", "helper", "subcontractor", "viewer", "guest", "customer")

_LEGACY_ROLE_MAP = {
    "admin": "admin",
    "administrator": "admin",
    "owner": "admin",
    "manager": "manager",
    "worker": "worker",
    "helper": "helper",
    "field_helper": "helper",
    "fieldhelper": "helper",
    "subcontractor": "subcontractor",
    "sub": "subcontractor",
    "1099": "subcontractor",
    "user": "viewer",
    "viewer": "viewer",
    "read-only": "viewer",
    "readonly": "viewer",
    "guest": "guest",
    "applicant": "guest",
    "non_company": "non_company",
    "non-company": "non_company",
    "external": "non_company",
    "customer": "customer",
}


def normalize_role(value: object) -> str:
    raw = (str(value or "")).strip().lower().replace("-", "_")
    if raw in _LEGACY_ROLE_MAP:
        return _LEGACY_ROLE_MAP[raw]
    return raw if raw in ROLE_LABELS else "viewer"


def role_display(value: object) -> str:
    return ROLE_DISPLAY.get(normalize_role(value), str(value or "viewer"))


def is_admin_role(value: object) -> bool:
    return normalize_role(value) == "admin"


def is_manager_or_admin(value: object) -> bool:
    return normalize_role(value) in {"admin", "manager"}


def migrate_user_roles(conn: sqlite3.Connection) -> int:
    """Normalize legacy capitalized or alias roles in users and online_sessions."""
    changed = 0
    rows = conn.execute("SELECT id, role FROM users").fetchall()
    for row in rows:
        old = row["role"] if isinstance(row, sqlite3.Row) else row[1]
        new = normalize_role(old)
        if new != (old or ""):
            uid = row["id"] if isinstance(row, sqlite3.Row) else row[0]
            conn.execute("UPDATE users SET role=? WHERE id=?", (new, uid))
            changed += 1
    try:
        sess = conn.execute("SELECT session_id, role FROM online_sessions").fetchall()
        for row in sess:
            old = row["role"]
            new = normalize_role(old)
            if new != (old or ""):
                conn.execute(
                    "UPDATE online_sessions SET role=? WHERE session_id=?",
                    (new, row["session_id"]),
                )
                changed += 1
    except sqlite3.Error:
        pass
    if changed:
        conn.commit()
    return changed


def ensure_role_normalization(conn: sqlite3.Connection) -> None:
    migrate_user_roles(conn)
