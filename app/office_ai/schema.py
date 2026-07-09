# -*- coding: utf-8 -*-
"""Office AI SQLite schema."""
from __future__ import annotations

import sqlite3


def ensure_office_ai_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS office_ai_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            title TEXT DEFAULT 'Office chat',
            provider TEXT DEFAULT 'openai',
            model TEXT DEFAULT 'gpt-4o',
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS office_ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_calls_json TEXT,
            created_at TEXT,
            FOREIGN KEY (session_id) REFERENCES office_ai_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS office_ai_pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            user_id INTEGER,
            username TEXT,
            tool_name TEXT NOT NULL,
            args_json TEXT,
            preview_text TEXT,
            status TEXT DEFAULT 'Pending',
            decided_by TEXT,
            decision_note TEXT,
            created_at TEXT,
            decided_at TEXT
        );
        CREATE TABLE IF NOT EXISTS office_ai_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            provider TEXT,
            model TEXT,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            cost_estimate REAL DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS office_ai_learning_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            summary TEXT NOT NULL,
            args_json TEXT,
            approved_by TEXT,
            created_at TEXT
        );
        """
    )
    conn.commit()
