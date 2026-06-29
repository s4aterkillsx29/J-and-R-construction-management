"""Log 403 East 2nd Jackie deck rebuild finish day for 2026-06-30.

Records correct 16 ft 2x4 joist lumber received/used and deck finish per plan.
Labor pay and material receipt amounts remain pending until owner provides details.

Runs without tkinter so it can be executed from headless/cloud environments.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EVIDENCE_DIR = BASE_DIR / "evidence"
DB_PATH = DATA_DIR / "jr_business.db"

WORK_DATE = "2026-06-30"
JOB_NAME = "403 East 2nd / Jackie deck rebuild"


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def iso_now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    EVIDENCE_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            status TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            date TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT,
            evidence_type TEXT,
            description TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS business_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            category TEXT NOT NULL,
            entry TEXT NOT NULL
        );
        """
    )
    conn.commit()


def update_job(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id, notes FROM jobs WHERE job_name=?", (JOB_NAME,)).fetchone()
    if not row:
        raise SystemExit(f"Job not found: {JOB_NAME}. Run prior Jackie deck log scripts first.")
    finish_note = (
        f"{WORK_DATE}: Finish day. Correct 16 ft 2x4 joists received and used for joists "
        "(replacement for returned 12 ft order). Deck finish completed per plan. "
        "Labor pay and lumber receipt/return amounts pending owner documents."
    )
    notes = (row["notes"] or "").strip()
    if finish_note not in notes:
        merged = f"{notes}\n\n{finish_note}".strip() if notes else finish_note
        conn.execute(
            "UPDATE jobs SET notes=?, updated_at=? WHERE id=?",
            (merged, iso_now(), row["id"]),
        )
        conn.commit()
    return row["id"]


def add_evidence(conn: sqlite3.Connection, *, job_id: int, file_name: str, file_path: str, description: str, notes: str) -> None:
    exists = conn.execute(
        "SELECT id FROM evidence WHERE file_name=? AND date=?",
        (file_name, WORK_DATE),
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO evidence(job_id, date, file_name, file_path, evidence_type, description, notes) "
        "VALUES(?,?,?,?,?,?,?)",
        (job_id, WORK_DATE, file_name, file_path, "Field Work Log", description, notes),
    )
    conn.commit()


def log_business(conn: sqlite3.Connection, entry: str) -> None:
    marker = f"Deck finish completed"
    exists = conn.execute(
        "SELECT id FROM business_log WHERE entry LIKE ? AND entry LIKE ?",
        (f"%{WORK_DATE}%", f"%{marker}%"),
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)",
        (now_stamp(), "Field Work", entry),
    )
    conn.commit()


def log_finish_day() -> None:
    conn = connect()
    ensure_schema(conn)
    job_id = update_job(conn)

    detail = f"""403 East 2nd / Jackie deck rebuild — Finish Day Log
Date: {WORK_DATE}

Materials:
- Correct 16 ft 2x4 joists received (reorder after 12 ft return on 2026-06-29)
- 16 ft joists used for deck framing

Progress:
- Deck finish completed per plan

Pending (owner to provide):
- Labor hours / helper pay for finish day
- Lumber purchase receipt and return credit amounts
"""
    path = EVIDENCE_DIR / "Jackie_Deck_Rebuild_Finish_Log_2026-06-30.txt"
    path.write_text(detail.strip() + "\n", encoding="utf-8")

    add_evidence(
        conn,
        job_id=job_id,
        file_name=path.name,
        file_path=str(path),
        description="Deck finish day — 16 ft joists installed, deck completed",
        notes="Labor pay and receipt amounts pending.",
    )
    log_business(
        conn,
        f"{JOB_NAME} ({WORK_DATE}): Finish day — 16 ft 2x4 joists received and used; deck finish completed. "
        "Labor and receipt amounts pending.",
    )
    conn.close()

    print("Jackie deck rebuild finish day logged:", DB_PATH)
    print(f"  Job: {JOB_NAME} (id={job_id})")
    print(f"  Date: {WORK_DATE}")
    print("  Status: Active — deck finish complete (payment/receipts pending)")
    print("  Pending: labor pay + lumber receipts")


if __name__ == "__main__":
    log_finish_day()
