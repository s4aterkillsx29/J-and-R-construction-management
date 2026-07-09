# -*- coding: utf-8 -*-
"""mobile_outbox + mobile_outbox_files tables."""
from __future__ import annotations

import sqlite3


def ensure_outbox_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mobile_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT,
            username TEXT NOT NULL,
            event_type TEXT NOT NULL,
            job_code TEXT,
            payload_json TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            processed_at TEXT,
            error_text TEXT
        );
        CREATE TABLE IF NOT EXISTS mobile_outbox_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outbox_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT,
            temp_path TEXT NOT NULL,
            dropbox_path TEXT,
            uploaded INTEGER DEFAULT 0,
            FOREIGN KEY(outbox_id) REFERENCES mobile_outbox(id)
        );
        """
    )
    conn.commit()
