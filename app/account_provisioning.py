"""Create role-appropriate profile rows when users are provisioned."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional


def now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def provision_user_role_profiles(
    conn: sqlite3.Connection,
    user_id: int,
    username: str,
    role: str,
    req: Optional[Any] = None,
) -> None:
    display_name = ""
    email = phone = address = worker_type = skills = emergency = ""
    preferred_rate = 0.0
    if req is not None:
        try:
            display_name = req["display_name"] or ""
            email = req["email"] or ""
            phone = req["phone"] or ""
            address = req["address"] or ""
            worker_type = req["worker_type"] or ""
            skills = req["skills"] or ""
            emergency = req["emergency_contact"] or ""
            preferred_rate = float(req["preferred_rate"] or 0)
        except Exception:
            pass

    if role in ("admin", "manager", "worker", "helper", "viewer"):
        conn.execute(
            """INSERT OR REPLACE INTO worker_user_profiles
               (user_id, username, display_name, email, phone, address, worker_type, skills, emergency_contact, preferred_rate, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, username, display_name, email, phone, address, worker_type, skills, emergency, preferred_rate, now_iso(), now_iso()),
        )
    if role == "customer":
        conn.execute(
            """INSERT OR REPLACE INTO customer_user_profiles
               (user_id, username, display_name, email, phone, address, portal_status, created_at, updated_at, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user_id, username, display_name, email, phone, address, "Active", now_iso(), now_iso(), "Provisioned from account request or admin setup."),
        )
