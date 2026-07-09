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


def _ensure_file_sources(conn: sqlite3.Connection) -> None:
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


def _ensure_job_applications(conn: sqlite3.Connection) -> None:
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
            date_of_birth TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            preferred_rate REAL DEFAULT 0,
            rate_type TEXT,
            availability TEXT,
            transportation TEXT,
            drivers_license_status TEXT,
            own_tools TEXT,
            skills TEXT,
            experience_years REAL DEFAULT 0,
            work_history TEXT,
            references_text TEXT,
            insurance_full_legal_name TEXT,
            insurance_address TEXT,
            insurance_phone TEXT,
            insurance_email TEXT,
            insurance_date_of_birth TEXT,
            insurance_driver_license_state TEXT,
            insurance_driver_license_number TEXT,
            insurance_vehicle_use TEXT,
            insurance_employment_classification TEXT,
            insurance_requested_coverage TEXT,
            insurance_notes TEXT,
            w9_status TEXT,
            id_document_status TEXT,
            request_ip TEXT,
            request_user_agent TEXT
        )
        """
    )
    text_columns = [
        "created_at",
        "updated_at",
        "status",
        "requested_username",
        "desired_role",
        "full_name",
        "email",
        "recovery_email",
        "phone",
        "address",
        "date_of_birth",
        "emergency_contact_name",
        "emergency_contact_phone",
        "rate_type",
        "availability",
        "transportation",
        "drivers_license_status",
        "own_tools",
        "skills",
        "work_history",
        "references_text",
        "insurance_full_legal_name",
        "insurance_address",
        "insurance_phone",
        "insurance_email",
        "insurance_date_of_birth",
        "insurance_driver_license_state",
        "insurance_driver_license_number",
        "insurance_vehicle_use",
        "insurance_employment_classification",
        "insurance_requested_coverage",
        "insurance_notes",
        "w9_status",
        "id_document_status",
        "request_ip",
        "request_user_agent",
    ]
    for column in text_columns:
        _ensure_column(conn, "job_applications", column, f"{column} TEXT")
    _ensure_column(conn, "job_applications", "preferred_rate", "preferred_rate REAL DEFAULT 0")
    _ensure_column(conn, "job_applications", "experience_years", "experience_years REAL DEFAULT 0")


def _repair() -> None:
    base = Path(__file__).resolve().parent
    data_dir = Path(os.environ.get("JRC_DATA_DIR", str(base / "data"))).expanduser()
    db_path = Path(os.environ.get("JRC_DB_PATH", str(data_dir / "jr_business.db"))).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        return

    try:
        from app.db_health import configure_sqlite_connection

        conn = sqlite3.connect(db_path, timeout=15)
        try:
            configure_sqlite_connection(conn)
            _ensure_file_sources(conn)
            _ensure_job_applications(conn)
            try:
                from app.schema_migrations import ensure_all_shared_schemas

                ensure_all_shared_schemas(conn)
            except Exception:
                pass
            conn.commit()
            _log(base, f"Startup schema repair checked OK: {db_path}")
        finally:
            conn.close()
            ck = None
            try:
                ck = sqlite3.connect(db_path, timeout=5)
                ck.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            finally:
                if ck is not None:
                    ck.close()
    except Exception as exc:
        _log(base, f"Startup schema repair warning: {exc}")


if os.environ.get("JRC_SKIP_STARTUP_REPAIR", "").strip().lower() not in ("1", "true", "yes"):
    _repair()
