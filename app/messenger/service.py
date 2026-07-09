# -*- coding: utf-8 -*-
"""Messenger send/list/mark read."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.messenger import permissions


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_sessions(conn: sqlite3.Connection, role: str) -> List[Dict[str, Any]]:
    allowed = permissions.allowed_channels(role)
    if not allowed:
        return []
    placeholders = ",".join("?" * len(allowed))
    rows = conn.execute(
        f"SELECT * FROM live_chat_sessions WHERE active=1 AND channel_type IN ({placeholders}) ORDER BY updated_at DESC",
        tuple(allowed),
    ).fetchall()
    return [dict(r) for r in rows]


def list_messages(conn: sqlite3.Connection, session_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM live_chat_messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def send_message(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    username: str,
    role: str,
    body: str,
    channel_type: str = "team",
) -> dict:
    if not permissions.can_send(role, channel_type):
        return {"ok": False, "error": "Not allowed to send in this channel"}
    body = (body or "").strip()
    if not body:
        return {"ok": False, "error": "Empty message"}
    ts = _now()
    conn.execute(
        "INSERT INTO live_chat_messages (session_id, username, role, body, created_at) VALUES (?,?,?,?,?)",
        (session_id, username, role, body, ts),
    )
    conn.execute(
        "UPDATE live_chat_sessions SET updated_at=? WHERE id=?",
        (ts, session_id),
    )
    conn.commit()
    return {"ok": True, "message": "Sent"}


def poll_updates(conn: sqlite3.Connection, session_id: int, after_id: int = 0) -> dict:
    rows = conn.execute(
        "SELECT * FROM live_chat_messages WHERE session_id=? AND id>? ORDER BY id",
        (session_id, after_id),
    ).fetchall()
    return {"ok": True, "messages": [dict(r) for r in rows]}
