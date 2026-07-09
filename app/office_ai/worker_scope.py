# -*- coding: utf-8 -*-
"""Phase 4 — worker-scoped AI (disabled by default; owner/admin only today)."""
from __future__ import annotations

import sqlite3

from app.office_ai.access import is_office_ai_user


def worker_ai_enabled(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key='office_ai_worker_enabled'").fetchone()
        return row and str(row[0]).strip() == "1"
    except Exception:
        return False


def can_use_worker_ai(user: dict, conn: sqlite3.Connection) -> bool:
    """When enabled, helpers/workers get read-only dashboard tools only."""
    if not worker_ai_enabled(conn):
        return False
    role = str(user.get("role") or "").lower()
    return role in {"helper", "worker", "viewer"}


def assert_office_ai_route(user: dict) -> bool:
    """Main Office AI remains owner/admin only regardless of worker flag."""
    return is_office_ai_user(user)
