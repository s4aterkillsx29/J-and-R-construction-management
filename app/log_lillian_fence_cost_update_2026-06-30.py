"""Log Lillian 315 dog ear fence internal cost update from owner field pad (2026-06-30).

Transcribes 2026-06-29 field cost pad into business log and refreshes log mirror.
Runs without tkinter for headless/cloud use.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "jr_business.db"
LOG_MIRROR = EXPORT_DIR / "JRC_Business_Log_Latest.txt"

JOB_ID = "JRC-JOB-315-LILLIAN-DOGEAR-FENCE"
CUSTOMER = "Lillian Cosentino"
ADDRESS = "315 Sassafras Lane"
WORK_DATE = "2026-06-29"
LOG_DATE = "2026-06-30"

ENTRY = (
    f"{LOG_DATE}: Internal cost pad synced for {JOB_ID} ({CUSTOMER}, {ADDRESS}). "
    "Dog ear fence — NOT chain link. Home Depot materials subtotal $3,212.61; "
    "field equipment $220; helper labor plan 2x$240/day x 10 days = $4,800; "
    "owner internal total $8,432.61. Customer price TBD. "
    "Rejected chain-link placeholder ($7,200 F&F) does not match this scope. "
    "Files: docs/internal/lillian-315-sassafras-dogear-fence/"
)


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def iso_now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    EXPORT_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS business_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            category TEXT NOT NULL,
            entry TEXT NOT NULL
        )
        """
    )
    conn.commit()


def write_log(conn: sqlite3.Connection) -> None:
    ts = iso_now()
    conn.execute(
        "INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)",
        (ts, "Job Cost / Quote", ENTRY),
    )
    conn.commit()


def refresh_mirror(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT timestamp, category, entry FROM business_log ORDER BY id DESC LIMIT 50"
    ).fetchall()
    lines = [f"J & R Construction — Business Log Mirror\nUpdated: {now_stamp()}\n"]
    for row in reversed(rows):
        lines.append(f"[{row['timestamp']}] {row['category']}: {row['entry']}")
    LOG_MIRROR.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    conn = connect()
    ensure_schema(conn)
    write_log(conn)
    refresh_mirror(conn)
    print("Logged:", ENTRY)
    print("Mirror:", LOG_MIRROR)


if __name__ == "__main__":
    main()
