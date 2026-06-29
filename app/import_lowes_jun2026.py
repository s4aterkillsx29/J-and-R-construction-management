"""Log Lowe's receipt evidence from June 2026 mobile app order screenshots.

Captures invoice-level expenses, line-item detail in evidence notes, and return credits.
PO 40 cumberland maps to the Ray Joyner / 42 Cumberland job.

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

STORE = "Shallotte Lowe's"
STORE_ADDRESS = "351 WHITEVILLE RD NW, Shallotte, NC 28470"
CATEGORY = "Materials & Supplies"
VENDOR = "Lowe's"
JOB_NAME = "Ray Joyner / 42 Cumberland"


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


def ensure_ray_job(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM jobs WHERE job_name=?", (JOB_NAME,)).fetchone()
    if row:
        return row["id"]
    customer_id = conn.execute(
        "INSERT INTO customers(name, phone, email, address, notes, created_at) VALUES(?,?,?,?,?,?)",
        ("Ray Joyner", "", "", "42 Cumberland", "Shower door customer; possible callback flag.", iso_now()),
    ).lastrowid
    return conn.execute(
        """INSERT INTO jobs(customer_id, job_name, job_address, status, scope, contract_price,
           deposit_required, deposit_paid, balance_paid, payment_method, callback_flag, notes, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            customer_id,
            JOB_NAME,
            "42 Cumberland",
            "Closed Paid",
            "Install three shower door units. Silicone cure and possible callback/warranty watch.",
            5000,
            2500,
            2500,
            2500,
            "Customer payment",
            1,
            "Follow-up text sent. Watch for water splashing/callback.",
            iso_now(),
            iso_now(),
        ),
    ).lastrowid


def add_expense(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    date: str,
    description: str,
    amount: float,
    receipt_status: str = "Receipt saved",
    notes: str = "",
) -> int | None:
    exists = conn.execute(
        "SELECT id FROM expenses WHERE date=? AND description=? AND amount=?",
        (date, description, amount),
    ).fetchone()
    if exists:
        return exists["id"]
    cur = conn.execute(
        "INSERT INTO expenses(job_id, date, vendor, category, description, amount, receipt_status, notes) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (job_id, date, VENDOR, CATEGORY, description, amount, receipt_status, notes),
    )
    conn.commit()
    return cur.lastrowid


def add_evidence(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    date: str,
    file_name: str,
    file_path: str,
    description: str,
    notes: str = "",
) -> int | None:
    exists = conn.execute(
        "SELECT id FROM evidence WHERE file_name=? AND date=?",
        (file_name, date),
    ).fetchone()
    if exists:
        return exists["id"]
    cur = conn.execute(
        "INSERT INTO evidence(job_id, date, file_name, file_path, evidence_type, description, notes) "
        "VALUES(?,?,?,?,?,?,?)",
        (job_id, date, file_name, file_path, "Receipt", description, notes),
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
        (now_stamp(), "Receipt Evidence", entry),
    )
    conn.commit()


def log_receipts() -> None:
    conn = connect()
    ensure_schema(conn)
    jid = ensure_ray_job(conn)
    conn.commit()

    inv_98662_detail = f"""Lowe's Order Details — Invoice 98662
Date: Wednesday, June 3, 2026
Store: {STORE}
Address: {STORE_ADDRESS}
PO: 40 cumberland
Status: Picked Up
Total: $443.23 (21 items)

Line items captured from receipt screenshots:
- Harbor Breeze 24-ft Plug-in Black Outdoor String Light w/ 12 LED Edison Bulbs — qty 5 @ $34.98 = $174.90
- Amerimax Aluminum 2-in White Adjustable Downspout band — qty 4 @ $1.98 = $7.92
- M-D Spline 0.175In X 25Ft Black — qty 1 = $6.58
- M-D 3-ft x 7-ft Charcoal Fiberglass Screen mesh — qty 1 = $9.98
- Gardner Bender 7/16-in Plastic Low-voltage Cable Staple 50-Pack — qty 2 @ $6.48 = $12.96
- Screen Tight 5 Bar Universal reversible 32x80 Natural Wood Screen door — qty 1, discount -$25.00 = $60.00
- Hillman #8 x 1-in Phillips Sheet Metal Screws 6-Count — qty 1 = $3.98
- Utilitech 8-in Nylon Extreme weather zip ties 100-Pack — qty 1 = $12.98
- Utilitech 15-ft 16/3 Light Duty 3 Prong Indoor Extension Cord — qty 2 @ $17.98 = $35.96
(Additional items in 13-item pickup section not fully visible in screenshots.)

Evidence source: Lowe's mobile app Order Details screenshots (Jun 2026).
"""
    path_98662 = write_evidence_file("Lowes_Invoice_98662_2026-06-03.txt", inv_98662_detail)
    add_expense(
        conn,
        job_id=jid,
        date="2026-06-03",
        description="Lowe's Invoice 98662 — Cumberland job materials (21 items)",
        amount=443.23,
        notes=f"PO 40 cumberland. {STORE}. Evidence: {path_98662.name}",
    )
    add_evidence(
        conn,
        job_id=jid,
        date="2026-06-03",
        file_name=path_98662.name,
        file_path=str(path_98662),
        description="Lowe's Invoice 98662 — $443.23 — PO 40 cumberland",
        notes="Mobile app order screenshot evidence. 21 items picked up.",
    )

    return_hb_detail = f"""Lowe's Return — Harbor Breeze String Light
Status: Return Completed
Item: Harbor Breeze 24-ft Plug-in Black Outdoor String Light with 12 White-Light LED Edison Bulbs
Quantity: 1
Subtotal: $34.98
Tax: $2.36
Total credit: $37.34
Payment method: Visa ending 6668

Related to Invoice 98662 (Jun 3, 2026).
Evidence source: Lowe's mobile app Order Details return screenshot.
"""
    path_return_hb = write_evidence_file("Lowes_Return_HarborBreeze_2026-06.txt", return_hb_detail)
    add_expense(
        conn,
        job_id=jid,
        date="2026-06-03",
        description="Lowe's return credit — Harbor Breeze string light (Inv 98662)",
        amount=-37.34,
        notes=f"Return Completed. Visa *6668. Evidence: {path_return_hb.name}",
    )
    add_evidence(
        conn,
        job_id=jid,
        date="2026-06-03",
        file_name=path_return_hb.name,
        file_path=str(path_return_hb),
        description="Lowe's return — Harbor Breeze string light — $37.34 credit",
        notes="Return Completed against Invoice 98662.",
    )

    inv_71355_detail = f"""Lowe's Order Details — Invoice 71355
Date: Thursday, June 4, 2026
Store: {STORE}
Address: {STORE_ADDRESS}
PO: na
Status: Picked Up
Items: 3

Line items:
- Gardner Bender 1/4-in Plastic Cable Staple 25-Pack — qty 3 @ $3.98 = $11.94

Subtotal: $11.94
Tax: $0.81
Total: $12.75

Evidence source: Lowe's mobile app Order Details screenshot.
"""
    path_71355 = write_evidence_file("Lowes_Invoice_71355_2026-06-04.txt", inv_71355_detail)
    add_expense(
        conn,
        job_id=jid,
        date="2026-06-04",
        description="Lowe's Invoice 71355 — cable staples (3 packs)",
        amount=12.75,
        notes=f"{STORE}. Evidence: {path_71355.name}",
    )
    add_evidence(
        conn,
        job_id=jid,
        date="2026-06-04",
        file_name=path_71355.name,
        file_path=str(path_71355),
        description="Lowe's Invoice 71355 — $12.75 — cable staples",
        notes="3x Gardner Bender 1/4-in cable staple 25-pack.",
    )

    inv_71336_detail = f"""Lowe's Order Details — Invoice 71336
Date: Thursday, June 4, 2026
Invoice: 71336
Items: 2
Status: Return Completed

Line items:
- Enbrighten Smart 125-Volt 2-Outlet Indoor/Outdoor Smart Plug — qty 2 @ $27.48 = $54.96

Subtotal: $54.96
Tax: $3.71
Total: $58.67

Note: Full order returned — net business cost $0.00.

Evidence source: Lowe's mobile app Order Details screenshot.
"""
    path_71336 = write_evidence_file("Lowes_Invoice_71336_2026-06-04.txt", inv_71336_detail)
    add_expense(
        conn,
        job_id=jid,
        date="2026-06-04",
        description="Lowe's Invoice 71336 — Enbrighten smart plugs (returned)",
        amount=58.67,
        notes="Purchase logged for audit trail. Return Completed — net $0.",
    )
    add_evidence(
        conn,
        job_id=jid,
        date="2026-06-04",
        file_name=path_71336.name,
        file_path=str(path_71336),
        description="Lowe's Invoice 71336 — $58.67 — smart plugs (returned)",
        notes="Return Completed. 2x Enbrighten Smart Plug.",
    )
    add_expense(
        conn,
        job_id=jid,
        date="2026-06-04",
        description="Lowe's return credit — Enbrighten smart plugs (Inv 71336)",
        amount=-58.67,
        notes=f"Return Completed — full order credit. Evidence: {path_71336.name}",
    )

    log_business(
        conn,
        "Logged Lowe's Jun 2026 receipt evidence: Inv 98662 ($443.23), return HB (-$37.34), "
        "Inv 71355 ($12.75), Inv 71336 ($58.67 returned). Assigned to Ray Joyner / 42 Cumberland.",
    )
    conn.close()

    print("Lowe's receipt evidence logged:", DB_PATH)
    print(f"  Job: {JOB_NAME} (id={jid})")
    print("  Net Lowe's materials from these receipts: $418.64")


if __name__ == "__main__":
    log_receipts()
