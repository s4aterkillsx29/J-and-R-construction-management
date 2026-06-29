"""Correct Jackie deck rebuild joist lumber order and log finish plan.

Wrong order: 12 ft 2x4 for joists. Correct spec: 16 ft 2x4 joists.
Wrong boards returned; correct lumber reordered for afternoon pickup 2026-06-29.
Deck finish planned for 2026-06-30.

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

CORRECTION_DATE = "2026-06-29"
FINISH_DATE = "2026-06-30"
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


def job_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id, notes FROM jobs WHERE job_name=?", (JOB_NAME,)).fetchone()
    if not row:
        raise SystemExit(f"Job not found: {JOB_NAME}. Run log_jackie_deck_rebuild_2026-06-29.py first.")
    correction_note = (
        f"{CORRECTION_DATE}: Joist lumber correction — wrong order was 12 ft 2x4 for joists; "
        "job needs 16 ft 2x4 joists. Returned wrong boards and reordered correct 16 ft lumber "
        f"(arriving afternoon {CORRECTION_DATE}). Plan to finish deck {FINISH_DATE}."
    )
    notes = (row["notes"] or "").strip()
    if correction_note not in notes:
        merged = f"{notes}\n\n{correction_note}".strip() if notes else correction_note
        conn.execute("UPDATE jobs SET notes=?, updated_at=? WHERE id=?", (merged, iso_now(), row["id"]))
        conn.commit()
    return row["id"]


def add_evidence(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    file_name: str,
    file_path: str,
    description: str,
    notes: str,
) -> None:
    exists = conn.execute(
        "SELECT id FROM evidence WHERE file_name=? AND date=?",
        (file_name, CORRECTION_DATE),
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO evidence(job_id, date, file_name, file_path, evidence_type, description, notes) "
        "VALUES(?,?,?,?,?,?,?)",
        (job_id, CORRECTION_DATE, file_name, file_path, "Materials Correction", description, notes),
    )
    conn.commit()


def log_business(conn: sqlite3.Connection, entry: str) -> None:
    marker = "Joist lumber correction"
    exists = conn.execute(
        "SELECT id FROM business_log WHERE entry LIKE ?",
        (f"%{marker}%",),
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)",
        (now_stamp(), "Materials", entry),
    )
    conn.commit()


def log_correction() -> None:
    conn = connect()
    ensure_schema(conn)
    jid = job_id(conn)

    detail = f"""403 East 2nd / Jackie deck rebuild — Joist Lumber Correction
Date: {CORRECTION_DATE}

Correction:
- Wrong order placed: 12 ft 2x4 lumber intended for joists
- Correct spec needed: 16 ft 2x4 joists
- Action taken: returned the wrong 12 ft boards and reordered correct 16 ft 2x4 joist lumber

Delivery:
- Correct 16 ft 2x4 joists expected this afternoon ({CORRECTION_DATE})

Schedule:
- Plan to finish deck: {FINISH_DATE}

Note: Receipt/return credit amounts to be logged when documents are available.
"""
    path = EVIDENCE_DIR / "Jackie_Deck_Rebuild_Materials_Correction_2026-06-29.txt"
    path.write_text(detail.strip() + "\n", encoding="utf-8")

    add_evidence(
        conn,
        job_id=jid,
        file_name=path.name,
        file_path=str(path),
        description="Joist lumber correction — returned 12 ft 2x4, reordered 16 ft 2x4 joists",
        notes=f"Correct lumber arriving afternoon {CORRECTION_DATE}. Finish deck planned {FINISH_DATE}.",
    )
    log_business(
        conn,
        f"{JOB_NAME}: Joist lumber correction — returned wrong 12 ft 2x4 joist order; "
        f"reordered 16 ft 2x4 joists (arriving afternoon {CORRECTION_DATE}). "
        f"Plan to finish deck {FINISH_DATE}.",
    )
    conn.close()

    print("Jackie deck rebuild materials correction logged:", DB_PATH)
    print(f"  Job: {JOB_NAME} (id={jid})")
    print("  Wrong: 12 ft 2x4 joists — returned")
    print("  Correct: 16 ft 2x4 joists — arriving this afternoon")
    print(f"  Finish planned: {FINISH_DATE}")


if __name__ == "__main__":
    log_correction()
