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


def ensure_unified_jobs_schema(conn: sqlite3.Connection) -> None:
    """Bridge desktop Office jobs columns (contract_price, job_address) to web host columns (price, address)."""
    cols = _columns(conn, "jobs")
    if not cols:
        return
    for name, typedef in (
        ("address", "TEXT"),
        ("scope", "TEXT"),
        ("price", "REAL DEFAULT 0"),
        ("deposit", "REAL DEFAULT 0"),
        ("paid", "REAL DEFAULT 0"),
        ("payment_method", "TEXT"),
        ("tax_status", "TEXT"),
        ("notes", "TEXT"),
        ("created_at", "TEXT"),
        ("updated_at", "TEXT"),
        ("job_address", "TEXT"),
        ("contract_price", "REAL DEFAULT 0"),
        ("deposit_required", "REAL DEFAULT 0"),
        ("deposit_paid", "REAL DEFAULT 0"),
        ("balance_paid", "REAL DEFAULT 0"),
        ("job_code", "TEXT"),
        ("office_folder_path", "TEXT"),
        ("office_status", "TEXT"),
    ):
        _add_col(conn, "jobs", name, typedef, cols)
        cols = _columns(conn, "jobs")
    conn.execute(
        """
        UPDATE jobs SET
            address = COALESCE(NULLIF(address, ''), job_address),
            job_address = COALESCE(NULLIF(job_address, ''), address),
            price = CASE WHEN COALESCE(price, 0) = 0 THEN COALESCE(contract_price, 0) ELSE price END,
            contract_price = CASE WHEN COALESCE(contract_price, 0) = 0 THEN COALESCE(price, 0) ELSE contract_price END,
            deposit = CASE WHEN COALESCE(deposit, 0) = 0 THEN COALESCE(deposit_required, 0) ELSE deposit END,
            deposit_required = CASE WHEN COALESCE(deposit_required, 0) = 0 THEN COALESCE(deposit, 0) ELSE deposit_required END,
            paid = CASE
                WHEN COALESCE(paid, 0) = 0 THEN COALESCE(balance_paid, 0) + COALESCE(deposit_paid, 0)
                ELSE paid
            END,
            updated_at = COALESCE(NULLIF(updated_at, ''), created_at)
        """
    )
    conn.commit()


def ensure_unified_expenses_schema(conn: sqlite3.Connection) -> None:
    cols = _columns(conn, "expenses")
    if not cols:
        return
    for name, typedef in (
        ("category", "TEXT"),
        ("vendor", "TEXT"),
        ("description", "TEXT"),
        ("amount", "REAL DEFAULT 0"),
        ("paid_by", "TEXT"),
        ("receipt_file", "TEXT"),
        ("receipt_status", "TEXT"),
        ("expense_date", "TEXT"),
        ("created_at", "TEXT"),
        ("date", "TEXT"),
        ("notes", "TEXT"),
    ):
        _add_col(conn, "expenses", name, typedef, cols)
        cols = _columns(conn, "expenses")
    conn.execute(
        """
        UPDATE expenses SET
            expense_date = COALESCE(NULLIF(expense_date, ''), date),
            date = COALESCE(NULLIF(date, ''), expense_date),
            description = COALESCE(NULLIF(description, ''), notes),
            notes = COALESCE(NULLIF(notes, ''), description),
            category = COALESCE(NULLIF(category, ''), 'General'),
            vendor = COALESCE(NULLIF(vendor, ''), paid_by),
            created_at = COALESCE(NULLIF(created_at, ''), expense_date, date)
        """
    )
    conn.commit()


def ensure_unified_file_index_schema(conn: sqlite3.Connection) -> None:
    cols = _columns(conn, "file_index")
    if not cols:
        return
    for name, typedef in (
        ("file_path", "TEXT"),
        ("file_name", "TEXT"),
        ("extension", "TEXT"),
        ("size", "INTEGER"),
        ("size_bytes", "INTEGER DEFAULT 0"),
        ("modified_at", "TEXT"),
        ("discovered_at", "TEXT"),
        ("indexed_at", "TEXT"),
        ("keywords", "TEXT"),
        ("analysis", "TEXT"),
        ("analysis_summary", "TEXT"),
        ("relative_path", "TEXT"),
        ("file_hash", "TEXT"),
    ):
        _add_col(conn, "file_index", name, typedef, cols)
        cols = _columns(conn, "file_index")
    conn.execute(
        """
        UPDATE file_index SET
            file_name = COALESCE(NULLIF(file_name, ''), relative_path, file_path),
            size = CASE WHEN COALESCE(size, 0) = 0 THEN COALESCE(size_bytes, 0) ELSE size END,
            size_bytes = CASE WHEN COALESCE(size_bytes, 0) = 0 THEN COALESCE(size, 0) ELSE size_bytes END,
            analysis = COALESCE(NULLIF(analysis, ''), analysis_summary),
            analysis_summary = COALESCE(NULLIF(analysis_summary, ''), analysis),
            discovered_at = COALESCE(NULLIF(discovered_at, ''), indexed_at, modified_at),
            indexed_at = COALESCE(NULLIF(indexed_at, ''), discovered_at, modified_at),
            keywords = COALESCE(keywords, '')
        """
    )
    conn.commit()


def ensure_all_shared_schemas(conn: sqlite3.Connection) -> None:
    ensure_unified_file_sources_schema(conn)
    ensure_unified_source_summaries_schema(conn)
    ensure_unified_jobs_schema(conn)
    ensure_unified_expenses_schema(conn)
    ensure_unified_file_index_schema(conn)
    try:
        from app.role_utils import ensure_role_normalization
        ensure_role_normalization(conn)
    except Exception:
        pass
