# -*- coding: utf-8 -*-
"""Guardian SQLite persistence — events, settings, job queue."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[2]


def _db_path() -> Path:
    import os

    data = os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))
    return Path(data) / "jr_business.db"


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS reliability_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT NOT NULL,
            level TEXT NOT NULL,
            profile TEXT,
            component TEXT,
            message TEXT,
            detail_json TEXT,
            fixed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS guardian_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS guardian_job_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queued_at TEXT NOT NULL,
            job_type TEXT NOT NULL,
            payload_json TEXT,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            finished_at TEXT,
            result_json TEXT
        );
        """
    )
    defaults = {
        "enabled": "1",
        "profile": "light",
        "auto_repair": "1",
        "paused_until": "",
    }
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO guardian_settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
    conn.commit()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM guardian_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO guardian_settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, now),
    )
    conn.commit()


def log_event(
    conn: sqlite3.Connection,
    *,
    level: str,
    component: str,
    message: str,
    profile: str = "",
    detail: Optional[Dict[str, Any]] = None,
    fixed: bool = False,
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO reliability_events (event_time, level, profile, component, message, detail_json, fixed) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (now, level, profile, component, message, json.dumps(detail or {}), 1 if fixed else 0),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def recent_events(conn: sqlite3.Connection, limit: int = 25) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM reliability_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def latest_status(conn: sqlite3.Connection) -> str:
    """Return green | yellow | red for Start Center chip."""
    if get_setting(conn, "enabled", "1") != "1":
        return "off"
    paused = get_setting(conn, "paused_until", "")
    if paused:
        try:
            if datetime.strptime(paused, "%Y-%m-%d %H:%M:%S") > datetime.now():
                return "paused"
        except ValueError:
            pass
    row = conn.execute(
        "SELECT level FROM reliability_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return "green"
    level = (row["level"] or "").upper()
    if level in ("ERROR", "CRITICAL"):
        return "red"
    if level in ("WARN", "WARNING"):
        return "yellow"
    return "green"
