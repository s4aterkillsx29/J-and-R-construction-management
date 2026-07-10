# -*- coding: utf-8 -*-
"""Messenger send/list/mark read."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.messenger import permissions


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_sessions(
    conn: sqlite3.Connection,
    role: str,
    *,
    username: str = "",
) -> List[Dict[str, Any]]:
    allowed = permissions.allowed_channels(role)
    if not allowed:
        return []
    placeholders = ",".join("?" * len(allowed))
    rows = conn.execute(
        f"""
        SELECT s.*
        FROM live_chat_sessions s
        WHERE s.active=1 AND s.channel_type IN ({placeholders})
        ORDER BY s.updated_at DESC
        """,
        tuple(allowed),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["unread"] = _unread_count(conn, int(r["id"]), username) if username else 0
        d["can_send"] = permissions.can_send(role, r["channel_type"] or "team")
        out.append(d)
    return out


def _unread_count(conn: sqlite3.Connection, session_id: int, username: str) -> int:
    row = conn.execute(
        "SELECT last_read_id FROM messenger_read_state WHERE username=? AND session_id=?",
        (username, session_id),
    ).fetchone()
    after = int(row["last_read_id"]) if row else 0
    return conn.execute(
        "SELECT COUNT(*) FROM live_chat_messages WHERE session_id=? AND id>?",
        (session_id, after),
    ).fetchone()[0]


def mark_read(conn: sqlite3.Connection, username: str, session_id: int) -> None:
    last = conn.execute(
        "SELECT MAX(id) FROM live_chat_messages WHERE session_id=?",
        (session_id,),
    ).fetchone()[0]
    if last is None:
        return
    conn.execute(
        """
        INSERT INTO messenger_read_state (username, session_id, last_read_id)
        VALUES (?,?,?)
        ON CONFLICT(username, session_id) DO UPDATE SET last_read_id=excluded.last_read_id
        """,
        (username, session_id, int(last)),
    )
    conn.commit()


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
    is_broadcast = 1 if channel_type in permissions.BROADCAST_CHANNELS else 0
    cur = conn.execute(
        """
        INSERT INTO live_chat_messages
        (session_id, username, role, body, is_admin_broadcast, created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (session_id, username, role, body, is_broadcast, ts),
    )
    conn.execute(
        "UPDATE live_chat_sessions SET updated_at=? WHERE id=?",
        (ts, session_id),
    )
    conn.commit()
    return {"ok": True, "message": "Sent", "id": int(cur.lastrowid)}


def poll_updates(conn: sqlite3.Connection, session_id: int, after_id: int = 0) -> dict:
    rows = conn.execute(
        "SELECT * FROM live_chat_messages WHERE session_id=? AND id>? ORDER BY id",
        (session_id, after_id),
    ).fetchall()
    return {"ok": True, "messages": [dict(r) for r in rows]}


def total_unread(conn: sqlite3.Connection, username: str, role: str) -> int:
    total = 0
    for sess in list_sessions(conn, role, username=username):
        total += int(sess.get("unread") or 0)
    return total


def find_or_create_dm(
    conn: sqlite3.Connection,
    user_a: str,
    user_b: str,
    *,
    created_by: str,
) -> int:
    a, b = sorted([user_a.strip(), user_b.strip()])
    row = conn.execute(
        "SELECT id, session_id FROM messenger_dm_threads WHERE user_a=? AND user_b=?",
        (a, b),
    ).fetchone()
    if row and row["session_id"]:
        return int(row["session_id"])
    ts = _now()
    title = f"DM: {a} & {b}"
    cur = conn.execute(
        """
        INSERT INTO live_chat_sessions (title, channel_type, created_by, active, created_at, updated_at)
        VALUES (?,?,?,1,?,?)
        """,
        (title, "dm", created_by, ts, ts),
    )
    sid = int(cur.lastrowid)
    conn.execute(
        """
        INSERT OR REPLACE INTO messenger_dm_threads (user_a, user_b, session_id, created_at)
        VALUES (?,?,?,?)
        """,
        (a, b, sid, ts),
    )
    conn.commit()
    return sid
