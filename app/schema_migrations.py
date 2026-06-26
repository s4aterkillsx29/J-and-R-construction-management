"""Unified SQLite schema helpers for desktop + web sharing one jr_business.db."""
from __future__ import annotations

import sqlite3
from typing import Set


def _columns(conn: sqlite3.Connection, table: str) -> Set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _add_col(conn: sqlite3.Connection, table: str, col: str, typedef: str, existing: Set[str]) -> None:
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")


def ensure_unified_file_sources_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT,
            source_name TEXT,
            source_type TEXT,
            folder_path TEXT,
            root_path TEXT,
            active INTEGER DEFAULT 1,
            enabled INTEGER DEFAULT 1,
            last_scan TEXT,
            notes TEXT,
            created_at TEXT
        )
        """
    )
    cols = _columns(conn, "file_sources")
    for name, typedef in (
        ("label", "TEXT"),
        ("source_name", "TEXT"),
        ("source_type", "TEXT"),
        ("folder_path", "TEXT"),
        ("root_path", "TEXT"),
        ("active", "INTEGER DEFAULT 1"),
        ("enabled", "INTEGER DEFAULT 1"),
        ("last_scan", "TEXT"),
        ("notes", "TEXT"),
        ("created_at", "TEXT"),
    ):
        _add_col(conn, "file_sources", name, typedef, cols)
        cols = _columns(conn, "file_sources")

    conn.execute(
        """
        UPDATE file_sources SET
            label = COALESCE(NULLIF(label, ''), source_name),
            source_name = COALESCE(NULLIF(source_name, ''), label),
            folder_path = COALESCE(NULLIF(folder_path, ''), root_path),
            root_path = COALESCE(NULLIF(root_path, ''), folder_path),
            active = COALESCE(active, enabled, 1),
            enabled = COALESCE(enabled, active, 1)
        """
    )
    conn.commit()


def ensure_unified_source_summaries_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            summary_key TEXT,
            summary_value TEXT,
            updated_at TEXT,
            summary_time TEXT,
            file_count INTEGER,
            total_size INTEGER,
            notes TEXT,
            FOREIGN KEY(source_id) REFERENCES file_sources(id)
        )
        """
    )
    cols = _columns(conn, "source_summaries")
    for name, typedef in (
        ("summary_key", "TEXT"),
        ("summary_value", "TEXT"),
        ("updated_at", "TEXT"),
        ("summary_time", "TEXT"),
        ("file_count", "INTEGER"),
        ("total_size", "INTEGER"),
        ("notes", "TEXT"),
    ):
        _add_col(conn, "source_summaries", name, typedef, cols)
        cols = _columns(conn, "source_summaries")
    conn.commit()


def get_or_create_internal_source(conn: sqlite3.Connection, name: str = "__Internal_Summary__") -> int:
    ensure_unified_file_sources_schema(conn)
    row = conn.execute(
        "SELECT id FROM file_sources WHERE source_name=? OR label=? LIMIT 1",
        (name, name),
    ).fetchone()
    if row:
        return int(row[0])
    conn.execute(
        """
        INSERT INTO file_sources (
            label, source_name, source_type, folder_path, root_path,
            active, enabled, notes, created_at
        ) VALUES (?, ?, 'internal', '', '', 1, 1, 'Internal summary bucket', datetime('now'))
        """,
        (name, name),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def ensure_all_shared_schemas(conn: sqlite3.Connection) -> None:
    ensure_unified_file_sources_schema(conn)
    ensure_unified_source_summaries_schema(conn)
