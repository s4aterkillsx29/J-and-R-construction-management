# -*- coding: utf-8 -*-
"""Messenger SQLite schema — extends live_chat."""
from __future__ import annotations

import sqlite3


def ensure_messenger_schema(conn: sqlite3.Connection) -> None:
    from app.live_chat import ensure_live_chat_schema

    ensure_live_chat_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS messenger_dm_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_a TEXT NOT NULL,
            user_b TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_a, user_b)
        );
        CREATE TABLE IF NOT EXISTS messenger_read_state (
            username TEXT NOT NULL,
            session_id INTEGER NOT NULL,
            last_read_id INTEGER DEFAULT 0,
            PRIMARY KEY (username, session_id)
        );
        """
    )
    conn.commit()
