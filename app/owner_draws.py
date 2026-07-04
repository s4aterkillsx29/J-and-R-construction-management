# -*- coding: utf-8 -*-
"""Owner draw (paid myself) tracking for J & R Construction sole proprietor."""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]

OWNER_DRAW_CSV_FIELDS = [
    "Date",
    "Amount",
    "Paid_From_Account",
    "Payment_Method",
    "Description",
    "Work_Type",
    "Notes",
]

DEFAULT_OFFICE_DAILY_RATE = "170"
DEFAULT_DRAW_ACCOUNT = "Business checking"
DEFAULT_WORK_TYPE = "Business office full day"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_owner_draws_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_draws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draw_date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            paid_from_account TEXT DEFAULT 'Business checking',
            payment_method TEXT,
            description TEXT,
            work_type TEXT,
            job_id INTEGER,
            notes TEXT,
            source TEXT DEFAULT 'manual',
            created_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.commit()


def _setting(conn: sqlite3.Connection, key: str, fallback: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return (row[0] if row else fallback) or fallback


def default_office_daily_amount(conn: sqlite3.Connection) -> float:
    raw = _setting(conn, "std_owner_office_daily_rate", DEFAULT_OFFICE_DAILY_RATE)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(DEFAULT_OFFICE_DAILY_RATE)


def default_draw_account(conn: sqlite3.Connection) -> str:
    return _setting(conn, "std_owner_draw_account", DEFAULT_DRAW_ACCOUNT) or DEFAULT_DRAW_ACCOUNT


def default_work_type(conn: sqlite3.Connection) -> str:
    return _setting(conn, "std_owner_draw_work_type", DEFAULT_WORK_TYPE) or DEFAULT_WORK_TYPE


def owner_draw_exists(
    conn: sqlite3.Connection,
    draw_date: str,
    amount: float,
    description: str = "",
) -> bool:
    row = conn.execute(
        """
        SELECT id FROM owner_draws
        WHERE draw_date=? AND ABS(amount - ?) < 0.01
          AND COALESCE(description, '')=?
        LIMIT 1
        """,
        (draw_date[:10], float(amount), description or ""),
    ).fetchone()
    return row is not None


def log_owner_draw(
    conn: sqlite3.Connection,
    *,
    draw_date: str,
    amount: float,
    description: str = "",
    paid_from_account: str = "",
    payment_method: str = "",
    work_type: str = "",
    job_id: Optional[int] = None,
    notes: str = "",
    source: str = "manual",
) -> int:
    """Insert an owner draw if the same date/amount/description is not already logged."""
    ensure_owner_draws_schema(conn)
    desc = (description or default_work_type(conn)).strip()
    account = (paid_from_account or default_draw_account(conn)).strip()
    wtype = (work_type or desc or default_work_type(conn)).strip()
    if owner_draw_exists(conn, draw_date, amount, desc):
        row = conn.execute(
            """
            SELECT id FROM owner_draws
            WHERE draw_date=? AND ABS(amount - ?) < 0.01
              AND COALESCE(description, '')=?
            LIMIT 1
            """,
            (draw_date[:10], float(amount), desc),
        ).fetchone()
        return int(row[0])

    conn.execute(
        """
        INSERT INTO owner_draws (
            draw_date, amount, paid_from_account, payment_method, description,
            work_type, job_id, notes, source, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            draw_date[:10],
            float(amount),
            account,
            payment_method or "",
            desc,
            wtype,
            job_id,
            notes or "",
            source,
            _now(),
        ),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def seed_owner_draws_from_office_records(conn: sqlite3.Connection) -> List[int]:
    """Seed owner draws aligned with Dropbox Owner_Draws_Register.csv."""
    entries = [
        (
            "2026-06-29",
            120.0,
            "403 Jackie deck rebuild — owner half day (band frame)",
            "Field half day",
            "JRC-403 day 1 band frame. Owner half day.",
        ),
        (
            "2026-06-30",
            240.0,
            "403 Jackie deck rebuild — owner full day 2 (deck finish)",
            "Field full day",
            "JRC-403 day 2 deck finish complete.",
        ),
        (
            "2026-07-01",
            170.0,
            "403 Jackie — business day while Wayne staining",
            "Business day while Wayne on site staining",
            "JRC-403 Wayne staining day. Standard $170 business day.",
        ),
    ]
    ids: List[int] = []
    for draw_date, amount, desc, wtype, notes in entries:
        ids.append(
            log_owner_draw(
                conn,
                draw_date=draw_date,
                amount=amount,
                description=desc,
                paid_from_account="Business checking",
                payment_method="Transfer",
                work_type=wtype,
                notes=notes,
                source="dropbox-office-csv",
            )
        )
    return ids


def seed_july_2_2026_office_draw(conn: sqlite3.Connection) -> Optional[int]:
    """Deprecated — use seed_owner_draws_from_office_records. Kept for compatibility."""
    ids = seed_owner_draws_from_office_records(conn)
    return ids[-1] if ids else None


def owner_draw_csv_path(dropbox: Path) -> Path:
    return dropbox / "06_bookkeeping" / "Owner_Draws_Register.csv"


def export_owner_draws_csv(conn: sqlite3.Connection, out_path: Path) -> int:
    ensure_owner_draws_schema(conn)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT draw_date, amount, paid_from_account, payment_method, description, work_type, notes
        FROM owner_draws
        WHERE COALESCE(source, '') != 'Office CSV'
          AND COALESCE(notes, '') NOT LIKE '%[office import]%'
        ORDER BY draw_date DESC, id DESC
        """
    ).fetchall()
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(OWNER_DRAW_CSV_FIELDS)
        for draw_date, amount, account, method, desc, wtype, notes in rows:
            writer.writerow(
                [
                    draw_date or "",
                    f"{float(amount or 0):.2f}",
                    account or "",
                    method or "",
                    desc or "",
                    wtype or "",
                    notes or "",
                ]
            )
    return len(rows)


def _normalize_amount(val: str) -> str:
    s = (val or "").strip().replace("$", "").replace(",", "")
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return s


def _draw_key(draw_date: str, amount: str, description: str) -> Tuple[str, str, str]:
    return ((draw_date or "").strip()[:10], _normalize_amount(amount), (description or "").strip().lower())


def import_owner_draws_from_office_csv(conn: sqlite3.Connection, dropbox: Path) -> Tuple[int, List[str]]:
    path = owner_draw_csv_path(dropbox)
    notes: List[str] = []
    if not path.is_file():
        return 0, [f"Missing owner draws register: {path}"]

    ensure_owner_draws_schema(conn)
    existing = {
        _draw_key(r[0], f"{r[1]:.2f}", r[2] or "")
        for r in conn.execute("SELECT draw_date, amount, description FROM owner_draws").fetchall()
    }
    imported = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            amount = _normalize_amount(row.get("Amount") or "0")
            try:
                amt = float(amount)
            except ValueError:
                continue
            if amt <= 0:
                continue
            draw_date = (row.get("Date") or "").strip() or _now()[:10]
            desc = (row.get("Description") or row.get("Work_Type") or "").strip()
            key = _draw_key(draw_date, amount, desc)
            if key in existing:
                continue
            note_parts = [row.get("Notes") or "", "[office import]"]
            log_owner_draw(
                conn,
                draw_date=draw_date,
                amount=amt,
                description=desc or default_work_type(conn),
                paid_from_account=(row.get("Paid_From_Account") or "").strip(),
                payment_method=(row.get("Payment_Method") or "").strip(),
                work_type=(row.get("Work_Type") or "").strip(),
                notes=" ".join(x for x in note_parts if x).strip(),
                source="Office CSV",
            )
            existing.add(key)
            imported += 1

    notes.append(f"owner draws imported from office: {imported} row(s)")
    return imported, notes


def total_owner_draws(conn: sqlite3.Connection) -> float:
    ensure_owner_draws_schema(conn)
    row = conn.execute("SELECT COALESCE(SUM(amount),0) FROM owner_draws").fetchone()
    return float(row[0] or 0) if row else 0.0


def _db_path() -> Path:
    data_dir = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
    return Path(os.environ.get("JRC_DB_PATH", str(data_dir / "jr_business.db"))).expanduser()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Log owner draws (paid myself) for J&R Construction.")
    sub = parser.add_subparsers(dest="cmd")

    log_p = sub.add_parser("log", help="Log a new owner draw")
    log_p.add_argument("--date", default=date.today().isoformat(), help="Draw date YYYY-MM-DD")
    log_p.add_argument("--amount", type=float, required=True, help="Amount paid to owner")
    log_p.add_argument("--description", default="", help="What the day/work was for")
    log_p.add_argument("--account", default="", help="Paid from account (default: business checking)")
    log_p.add_argument("--method", default="", help="Payment method")
    log_p.add_argument("--notes", default="", help="Extra notes")

    sub.add_parser("seed-today", help="Seed the 2026-07-02 $170 office draw if missing")
    sub.add_parser("list", help="List recent owner draws")

    args = parser.parse_args(argv)
    db_path = _db_path()
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        if args.cmd == "log":
            draw_id = log_owner_draw(
                conn,
                draw_date=args.date,
                amount=args.amount,
                description=args.description,
                paid_from_account=args.account,
                payment_method=args.method,
                notes=args.notes,
                source="cli",
            )
            print(f"Logged owner draw id={draw_id} ${args.amount:.2f} on {args.date[:10]}")
            return 0
        if args.cmd == "seed-today":
            draw_id = seed_july_2_2026_office_draw(conn)
            print(f"Owner draw ready id={draw_id} ($170 business office full day, 2026-07-02)")
            return 0
        if args.cmd == "list":
            ensure_owner_draws_schema(conn)
            rows = conn.execute(
                "SELECT draw_date, amount, paid_from_account, description FROM owner_draws ORDER BY draw_date DESC, id DESC LIMIT 20"
            ).fetchall()
            for d, a, acct, desc in rows:
                print(f"{d}  ${float(a):.2f}  {acct}  {desc}")
            return 0
        parser.print_help()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
