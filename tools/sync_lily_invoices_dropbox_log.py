#!/usr/bin/env python3
"""Save Lily 315 customer invoice copies to Dropbox and refresh the business log."""

from __future__ import annotations

import datetime as dt
import shutil
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "jr_business.db"
DOCS_DIR = BASE_DIR / "docs" / "quotes" / "lily-315-sassafras"
DEFAULT_DROPBOX_BUSINESS_ROOT = BASE_DIR / "dropbox_business"
LOG_MIRROR_FILENAME = "JRC_Business_Log_Latest.txt"
DROPBOX_DOCS_SUBDIR = "02_Documents_Invoices_Estimates_Quotes/Lily_315_Sassafras_Stairs"
DROPBOX_ORGANIZATION_FOLDERS = [
    "00_INBOX_To_File",
    "01_Jobs/Active",
    "01_Jobs/Completed",
    "01_Jobs/Leads_Estimates",
    "02_Documents_Invoices_Estimates_Quotes",
    "03_Receipts_Materials/Needs_Review",
    "03_Receipts_Materials/Filed",
    "04_Photos_Evidence/Before",
    "04_Photos_Evidence/During",
    "04_Photos_Evidence/After",
    "05_Helper_Pay_Workers",
    "06_Bookkeeping_Taxes/Income",
    "06_Bookkeeping_Taxes/Expenses",
    "06_Bookkeeping_Taxes/Schedule_C",
    "07_Backups",
    "08_Admin_Standards",
    "09_Archive",
    "10_Logs",
    "11_Exports",
    "12_Imports_ChatGPT",
]
INVOICE_SPECS = [
    {
        "doc_no": "INV-JRC-JOB-315-LILY-STAIR-SET-01-001",
        "job_name": "Lily / 315 Sassafras — Stair Set 1",
        "customer_copy_name": "CUSTOMER_COPY_INV-JRC-JOB-315-LILY-STAIR-SET-01-001.pdf",
    },
    {
        "doc_no": "INV-JRC-JOB-315-LILY-STAIR-SET-02-001",
        "job_name": "Lily / 315 Sassafras — Stair Set 2",
        "customer_copy_name": "CUSTOMER_COPY_INV-JRC-JOB-315-LILY-STAIR-SET-02-001.pdf",
    },
]


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")


def iso_now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def ensure_dropbox_organization(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel in DROPBOX_ORGANIZATION_FOLDERS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    readme = root / "_JRC_DROPBOX_ORGANIZATION_README.txt"
    if not readme.exists():
        readme.write_text(
            "J & R Construction Dropbox organization\n\n"
            "Single Dropbox business root for J&R records, invoices, logs, and job files.\n",
            encoding="utf-8",
        )
    return root


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS business_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            category TEXT,
            entry TEXT
        );
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
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    conn.commit()


def mirror_business_log(conn: sqlite3.Connection, dropbox_root: Path) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        "SELECT timestamp, category, entry FROM business_log ORDER BY id DESC LIMIT 250"
    ).fetchall()
    lines = [
        "J and R Construction Manager business log mirror",
        f"Updated: {now_stamp()}",
        "",
    ]
    for timestamp, category, entry in reversed(rows):
        lines.append(f"[{timestamp}] {category}: {entry}")
    mirror_path = EXPORT_DIR / LOG_MIRROR_FILENAME
    mirror_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    dropbox_logs = dropbox_root / "10_Logs"
    dropbox_logs.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mirror_path, dropbox_logs / LOG_MIRROR_FILENAME)
    shutil.copy2(mirror_path, dropbox_root / LOG_MIRROR_FILENAME)
    return mirror_path


def log_entry(conn: sqlite3.Connection, category: str, entry: str, dropbox_root: Path) -> None:
    conn.execute(
        "INSERT INTO business_log(timestamp, category, entry) VALUES(?,?,?)",
        (now_stamp(), category, entry),
    )
    conn.commit()
    mirror_business_log(conn, dropbox_root)


def ensure_lily_records(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM customers WHERE name=?", ("Lily / 315 Sassafras",)).fetchone()
    if row:
        customer_id = row[0]
    else:
        cur = conn.execute(
            "INSERT INTO customers(name, phone, email, address, notes, created_at) VALUES(?,?,?,?,?,?)",
            (
                "Lily / 315 Sassafras",
                "",
                "",
                "315 Sassafras Lane",
                "Friends & family customer. Possible large fence job follow-on.",
                iso_now(),
            ),
        )
        customer_id = cur.lastrowid
        conn.commit()

    scope = (
        "4-step exterior stair rebuild. Each step uses two 2x6 treads (8 treads total). "
        "1x8 kickplates, 3 pocket-cut stringers, 2x4 handrail, ~4 ft wide. Solo owner labor."
    )
    for spec in INVOICE_SPECS:
        row = conn.execute("SELECT id FROM jobs WHERE job_name=?", (spec["job_name"],)).fetchone()
        if row:
            continue
        conn.execute(
            """INSERT INTO jobs(
                customer_id, job_name, job_address, status, scope, contract_price,
                deposit_required, deposit_paid, balance_paid, payment_method, callback_flag,
                notes, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                customer_id,
                spec["job_name"],
                "315 Sassafras Lane",
                "Estimate Sent",
                scope,
                1000,
                500,
                0,
                0,
                "50/50",
                0,
                "Friends & family price $1,000 per stair set. Customer invoice saved to Dropbox.",
                iso_now(),
                iso_now(),
            ),
        )
    conn.commit()


def latest_invoice_pdf(doc_no: str) -> Path:
    matches = sorted(DOCS_DIR.glob(f"{doc_no}_*.pdf"))
    if not matches:
        raise FileNotFoundError(f"Missing invoice PDF for {doc_no} in {DOCS_DIR}")
    return matches[-1]


def save_customer_copies(dropbox_root: Path) -> list[Path]:
    target_dir = dropbox_root / DROPBOX_DOCS_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for spec in INVOICE_SPECS:
        source = latest_invoice_pdf(spec["doc_no"])
        dest = target_dir / spec["customer_copy_name"]
        shutil.copy2(source, dest)
        saved.append(dest)
    return saved


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(conn)
        configured = get_setting(conn, "dropbox_folder", "").strip()
        if configured:
            dropbox_root = Path(configured).expanduser()
        else:
            dropbox_root = DEFAULT_DROPBOX_BUSINESS_ROOT
            set_setting(conn, "dropbox_folder", str(dropbox_root))
        dropbox_root = ensure_dropbox_organization(dropbox_root)

        ensure_lily_records(conn)
        saved_paths = save_customer_copies(dropbox_root)

        log_entry(
            conn,
            "Document",
            "Lily / 315 Sassafras Lane — saved two customer-copy stair invoices to Dropbox "
            f"({DROPBOX_DOCS_SUBDIR}). "
            "INV-JRC-JOB-315-LILY-STAIR-SET-01-001 and INV-JRC-JOB-315-LILY-STAIR-SET-02-001 at "
            "$1,000.00 each (friends & family rate). Each 4-step set uses two 2x6 treads per step "
            f"(8 tread boards per set), 1x8 kickplates, 3 pocket stringers, 2x4 handrail. "
            f"Dropbox business root: {dropbox_root}",
            dropbox_root,
        )
        log_entry(
            conn,
            "Dropbox",
            f"Configured Dropbox business root and mirrored business log to {dropbox_root}",
            dropbox_root,
        )

        print(f"Dropbox root: {dropbox_root}")
        print(f"Log mirror: {EXPORT_DIR / LOG_MIRROR_FILENAME}")
        print(f"Dropbox log: {dropbox_root / '10_Logs' / LOG_MIRROR_FILENAME}")
        for path in saved_paths:
            print(f"Customer copy: {path}")
        print(f"Completed: {now_stamp()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
