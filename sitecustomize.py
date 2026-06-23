"""JRC safe startup schema repair.

Python loads this file automatically when commands are run from the program folder.
It performs only small, safe SQLite schema repairs before app.network_server starts.
This prevents older preserved business databases from crashing the local host when
newer code expects added columns.
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


def _log(base: Path, message: str) -> None:
    try:
        log_dir = base / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "startup_schema_repair.log").open("a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _repair() -> None:
    base = Path(__file__).resolve().parent
    data_dir = Path(os.environ.get("JRC_DATA_DIR", str(base / "data"))).expanduser()
    db_path = Path(os.environ.get("JRC_DB_PATH", str(data_dir / "jr_business.db"))).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        return

    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL DEFAULT '',
                    source_type TEXT,
                    folder_path TEXT NOT NULL DEFAULT '',
                    active INTEGER DEFAULT 1,
                    created_at TEXT
                )
                """
            )
            _ensure_column(conn, "file_sources", "label", "label TEXT NOT NULL DEFAULT ''")
            _ensure_column(conn, "file_sources", "source_type", "source_type TEXT")
            _ensure_column(conn, "file_sources", "folder_path", "folder_path TEXT NOT NULL DEFAULT ''")
            _ensure_column(conn, "file_sources", "active", "active INTEGER DEFAULT 1")
            _ensure_column(conn, "file_sources", "created_at", "created_at TEXT")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT,
                    updated_at TEXT,
                    status TEXT DEFAULT 'Pending Owner Review',
                    requested_username TEXT,
                    desired_role TEXT DEFAULT 'worker',
                    full_name TEXT,
                    email TEXT,
                    recovery_email TEXT,
                    phone TEXT,
                    address TEXT,
                    notes TEXT
                )
                """
            )
            conn.commit()
            _log(base, f"Startup schema repair checked OK: {db_path}")
        finally:
            conn.close()
    except Exception as exc:
        _log(base, f"Startup schema repair warning: {exc}")


_repair()
