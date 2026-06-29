"""Log 403 East 2nd Jackie deck rebuild field work for 2026-06-29.

Records half-day progress (2x4 band frame installed and staked down), helper Jesse pay,
owner half-day labor, and opening deposits to new business checking and tax savings accounts.

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

WORK_DATE = "2026-06-29"
CUSTOMER_NAME = "Jackie / 403 East 2nd OIB"
JOB_NAME = "403 East 2nd / Jackie deck rebuild"
JOB_ADDRESS = "403 East 2nd, Ocean Isle Beach"
HELPER_NAME = "Jesse"
OWNER_HALF_DAY_PAY = 120.0
HELPER_HALF_DAY_PAY = 120.0
CHECKING_DEPOSIT = 100.0
TAX_SAVINGS_DEPOSIT = 100.0
OWNER_RATE = 30.0
OWNER_HOURS = OWNER_HALF_DAY_PAY / OWNER_RATE


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
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            job_name TEXT NOT NULL,
            job_address TEXT,
            status TEXT NOT NULL,
            scope TEXT,
            contract_price REAL DEFAULT 0,
            deposit_required REAL DEFAULT 0,
            deposit_paid REAL DEFAULT 0,
            balance_paid REAL DEFAULT 0,
            payment_method TEXT,
            callback_flag INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            default_day_rate REAL DEFAULT 140,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS worker_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER,
            job_id INTEGER,
            date TEXT NOT NULL,
            work_description TEXT,
            amount REAL NOT NULL DEFAULT 0,
            payment_method TEXT,
            status TEXT DEFAULT 'Paid',
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS owner_labor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            date TEXT NOT NULL,
            hours REAL DEFAULT 0,
            rate REAL DEFAULT 30,
            description TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            date TEXT NOT NULL,
            vendor TEXT,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            receipt_status TEXT,
            notes TEXT
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


def ensure_customer(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM customers WHERE name=?", (CUSTOMER_NAME,)).fetchone()
    if row:
        return row["id"]
    return conn.execute(
        "INSERT INTO customers(name, phone, email, address, notes, created_at) VALUES(?,?,?,?,?,?)",
        (
            CUSTOMER_NAME,
            "",
            "",
            JOB_ADDRESS,
            "Cash expected; deck rebuild active at 403 East 2nd OIB.",
            iso_now(),
        ),
    ).lastrowid


def ensure_job(conn: sqlite3.Connection, customer_id: int) -> int:
    row = conn.execute("SELECT id, notes FROM jobs WHERE job_name=?", (JOB_NAME,)).fetchone()
    progress_note = (
        f"{WORK_DATE}: 2x4 band frame installed and staked down. Half-day crew work logged. "
        "Owner opened business checking and tax savings accounts; $100 deposited to each from job funds."
    )
    if row:
        jid = row["id"]
        notes = (row["notes"] or "").strip()
        if progress_note not in notes:
            merged = f"{notes}\n\n{progress_note}".strip() if notes else progress_note
            conn.execute(
                "UPDATE jobs SET status=?, notes=?, updated_at=? WHERE id=?",
                ("Active", merged, iso_now(), jid),
            )
            conn.commit()
        return jid
    return conn.execute(
        """INSERT INTO jobs(customer_id, job_name, job_address, status, scope, contract_price,
           deposit_required, deposit_paid, balance_paid, payment_method, callback_flag, notes, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            customer_id,
            JOB_NAME,
            JOB_ADDRESS,
            "Active",
            "Deck rebuild at 403 East 2nd OIB. Separate from exterior/demo approved scope.",
            0,
            0,
            0,
            0,
            "Cash expected",
            0,
            progress_note,
            iso_now(),
            iso_now(),
        ),
    ).lastrowid


def ensure_worker(conn: sqlite3.Connection, name: str, notes: str) -> int:
    row = conn.execute("SELECT id FROM workers WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    return conn.execute(
        "INSERT INTO workers(name, default_day_rate, notes, created_at) VALUES(?,?,?,?)",
        (name, 140.0, notes, iso_now()),
    ).lastrowid


def add_worker_payment(
    conn: sqlite3.Connection,
    *,
    worker_id: int,
    job_id: int,
    description: str,
    amount: float,
    notes: str,
) -> int | None:
    exists = conn.execute(
        "SELECT id FROM worker_payments WHERE worker_id=? AND job_id=? AND date=? AND work_description=? AND amount=?",
        (worker_id, job_id, WORK_DATE, description, amount),
    ).fetchone()
    if exists:
        return exists["id"]
    cur = conn.execute(
        "INSERT INTO worker_payments(worker_id, job_id, date, work_description, amount, payment_method, status, notes) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (worker_id, job_id, WORK_DATE, description, amount, "Cash", "Paid", notes),
    )
    conn.commit()
    return cur.lastrowid


def add_owner_labor(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    description: str,
    hours: float,
    rate: float,
    notes: str,
) -> int | None:
    exists = conn.execute(
        "SELECT id FROM owner_labor WHERE job_id=? AND date=? AND description=?",
        (job_id, WORK_DATE, description),
    ).fetchone()
    if exists:
        return exists["id"]
    cur = conn.execute(
        "INSERT INTO owner_labor(job_id, date, hours, rate, description, notes) VALUES(?,?,?,?,?,?)",
        (job_id, WORK_DATE, hours, rate, description, notes),
    )
    conn.commit()
    return cur.lastrowid


def add_expense(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    vendor: str,
    category: str,
    description: str,
    amount: float,
    notes: str,
) -> int | None:
    exists = conn.execute(
        "SELECT id FROM expenses WHERE job_id=? AND date=? AND description=? AND amount=?",
        (job_id, WORK_DATE, description, amount),
    ).fetchone()
    if exists:
        return exists["id"]
    cur = conn.execute(
        "INSERT INTO expenses(job_id, date, vendor, category, description, amount, receipt_status, notes) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (job_id, WORK_DATE, vendor, category, description, amount, "Pending documents", notes),
    )
    conn.commit()
    return cur.lastrowid


def add_evidence(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    file_name: str,
    file_path: str,
    description: str,
    notes: str = "",
) -> int | None:
    exists = conn.execute(
        "SELECT id FROM evidence WHERE file_name=? AND date=?",
        (file_name, WORK_DATE),
    ).fetchone()
    if exists:
        return exists["id"]
    cur = conn.execute(
        "INSERT INTO evidence(job_id, date, file_name, file_path, evidence_type, description, notes) "
        "VALUES(?,?,?,?,?,?,?)",
        (job_id, WORK_DATE, file_name, file_path, "Field Work Log", description, notes),
    )
    conn.commit()
    return cur.lastrowid


def write_evidence_file(name: str, body: str) -> Path:
    path = EVIDENCE_DIR / name
    if not path.exists():
        path.write_text(body.strip() + "\n", encoding="utf-8")
    return path


def log_business(conn: sqlite3.Connection, entry: str) -> None:
    conn.execute(
        "INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)",
        (now_stamp(), "Field Work", entry),
    )
    conn.commit()


def log_field_work() -> None:
    conn = connect()
    ensure_schema(conn)

    customer_id = ensure_customer(conn)
    job_id = ensure_job(conn, customer_id)
    jesse_id = ensure_worker(
        conn,
        HELPER_NAME,
        "New helper on 403 East 2nd Jackie deck rebuild. Paid $120 for half day on first work date.",
    )

    field_detail = f"""403 East 2nd / Jackie deck rebuild — Field Work Log
Date: {WORK_DATE}
Crew: Jacob Cosentino (owner) + Jesse (helper, first day)
Time on site: Half day

Progress:
- 2x4 band frame installed
- Band frame staked down

Labor paid from job funds:
- Jesse helper half day: ${HELPER_HALF_DAY_PAY:.2f} cash
- Owner half day: ${OWNER_HALF_DAY_PAY:.2f}

Business banking setup (funded from this job):
- Opened business checking account — deposited ${CHECKING_DEPOSIT:.2f}
- Opened tax savings account — deposited ${TAX_SAVINGS_DEPOSIT:.2f}

Documents: Owner will provide account setup documents when available.
"""
    evidence_path = write_evidence_file("Jackie_Deck_Rebuild_Field_Log_2026-06-29.txt", field_detail)
    add_evidence(
        conn,
        job_id=job_id,
        file_name=evidence_path.name,
        file_path=str(evidence_path),
        description="Half-day deck rebuild progress — 2x4 band frame installed and staked",
        notes="Jesse first helper day. Business checking and tax savings accounts opened.",
    )

    add_worker_payment(
        conn,
        worker_id=jesse_id,
        job_id=job_id,
        description="Helper labor — half day deck rebuild band frame",
        amount=HELPER_HALF_DAY_PAY,
        notes="New helper Jesse. Paid cash for half day on band frame install/staking.",
    )
    add_owner_labor(
        conn,
        job_id=job_id,
        description="Owner labor — half day deck rebuild band frame",
        hours=OWNER_HOURS,
        rate=OWNER_RATE,
        notes=f"Owner half-day pay ${OWNER_HALF_DAY_PAY:.2f}. Job-costing only for sole proprietor.",
    )
    add_expense(
        conn,
        job_id=job_id,
        vendor="Business Checking Account",
        category="Banking / Business Setup",
        description="Opening deposit — business checking account",
        amount=CHECKING_DEPOSIT,
        notes="Funded from 403 East 2nd Jackie deck rebuild job cash. Account documents pending.",
    )
    add_expense(
        conn,
        job_id=job_id,
        vendor="Tax Savings Account",
        category="Banking / Business Setup",
        description="Opening deposit — tax savings account",
        amount=TAX_SAVINGS_DEPOSIT,
        notes="Funded from 403 East 2nd Jackie deck rebuild job cash. Account documents pending.",
    )

    log_business(
        conn,
        f"{JOB_NAME} ({WORK_DATE}): 2x4 band frame installed and staked down. "
        f"Half day — Jesse ${HELPER_HALF_DAY_PAY:.0f}, owner ${OWNER_HALF_DAY_PAY:.0f}. "
        f"Opened business checking + tax savings; ${CHECKING_DEPOSIT:.0f} each from job funds.",
    )
    conn.close()

    print("Jackie deck rebuild field work logged:", DB_PATH)
    print(f"  Job: {JOB_NAME} (id={job_id})")
    print(f"  Helper: {HELPER_NAME} — ${HELPER_HALF_DAY_PAY:.2f}")
    print(f"  Owner labor: {OWNER_HOURS:.1f} hr @ ${OWNER_RATE:.2f} = ${OWNER_HALF_DAY_PAY:.2f}")
    print(f"  Account deposits: ${CHECKING_DEPOSIT:.2f} checking + ${TAX_SAVINGS_DEPOSIT:.2f} tax savings")


if __name__ == "__main__":
    log_field_work()
