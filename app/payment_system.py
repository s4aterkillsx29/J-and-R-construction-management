"""Debit payment requests, 5% fee, holds, ledger, and admin withdrawals."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEBIT_CARD_FEE_RATE = float(os.environ.get("JRC_DEBIT_FEE_RATE", "0.05"))
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
DB_PATH = Path(os.environ.get("JRC_DB_PATH", str(DATA_DIR / "jr_business.db"))).expanduser()


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def money(value: Any) -> float:
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def ensure_payment_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS debit_payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_code TEXT UNIQUE,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            amount REAL NOT NULL,
            fee_rate REAL DEFAULT 0.05,
            fee_amount REAL DEFAULT 0,
            total_due REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            reason TEXT,
            status TEXT DEFAULT 'Pending',
            payment_method TEXT DEFAULT 'debit_card',
            stripe_checkout_url TEXT,
            stripe_session_id TEXT,
            payer_reference TEXT,
            created_by TEXT,
            created_at TEXT,
            paid_at TEXT,
            confirmed_by TEXT,
            confirmed_at TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS business_funds_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_time TEXT,
            entry_type TEXT,
            amount REAL NOT NULL,
            fee_amount REAL DEFAULT 0,
            balance_after REAL,
            related_table TEXT,
            related_id INTEGER,
            description TEXT,
            created_by TEXT
        );
        CREATE TABLE IF NOT EXISTS admin_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            withdrawal_time TEXT,
            amount REAL NOT NULL,
            method TEXT,
            destination TEXT,
            status TEXT DEFAULT 'Completed',
            notes TEXT,
            created_by TEXT
        );
        """
    )
    for coldef in [
        "access_locked INTEGER DEFAULT 0",
        "lock_reason TEXT",
        "locked_payment_request_id INTEGER",
        "stripe_session_id TEXT",
    ]:
        try:
            conn.execute(f"ALTER TABLE debit_payment_requests ADD COLUMN {coldef}")
        except Exception:
            pass
    for coldef in [
        "access_locked INTEGER DEFAULT 0",
        "lock_reason TEXT",
        "locked_payment_request_id INTEGER",
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {coldef}")
        except Exception:
            pass
    conn.commit()


def calc_debit_total(amount: float) -> Tuple[float, float, float]:
    base = money(amount)
    fee = money(base * DEBIT_CARD_FEE_RATE)
    total = money(base + fee)
    return base, fee, total


def funds_balance(conn: sqlite3.Connection) -> float:
    row = conn.execute("SELECT COALESCE(SUM(amount),0) FROM business_funds_ledger").fetchone()
    return money(row[0] if row else 0)


def create_payment_request(
    conn: sqlite3.Connection,
    user_id: int,
    username: str,
    amount: float,
    reason: str,
    created_by: str,
    lock_until_paid: bool = True,
) -> Dict[str, Any]:
    base, fee, total = calc_debit_total(amount)
    code = "JRC-" + uuid.uuid4().hex[:10].upper()
    conn.execute(
        """INSERT INTO debit_payment_requests
           (request_code, user_id, username, amount, fee_rate, fee_amount, total_due, reason, status, created_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (code, user_id, username, base, DEBIT_CARD_FEE_RATE, fee, total, reason, "Pending", created_by, now_iso()),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    if lock_until_paid:
        conn.execute(
            "UPDATE users SET access_locked=1, lock_reason=?, locked_payment_request_id=? WHERE id=?",
            (f"Payment required: {reason}", req_id, user_id),
        )
    conn.commit()
    checkout_url = ""
    session_id = ""
    if os.environ.get("STRIPE_SECRET_KEY"):
        from app.stripe_integration import create_checkout_session
        base_url = os.environ.get("STRIPE_SUCCESS_URL", "").rstrip("/")
        if not base_url:
            cloud = os.environ.get("JRC_CLOUD_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
            base_url = f"{cloud}/payments/complete"
        ok, checkout_url, session_id = create_checkout_session(code, int(total * 100), username, base_url)
        if not ok:
            checkout_url = ""
    if checkout_url:
        conn.execute(
            "UPDATE debit_payment_requests SET stripe_checkout_url=?, stripe_session_id=? WHERE id=?",
            (checkout_url, session_id, req_id),
        )
        conn.commit()
    return {
        "id": req_id,
        "request_code": code,
        "amount": base,
        "fee_amount": fee,
        "total_due": total,
        "stripe_checkout_url": checkout_url,
        "stripe_session_id": session_id,
    }


def user_has_payment_lock(conn: sqlite3.Connection, user_id: int) -> Optional[sqlite3.Row]:
    row = conn.execute("SELECT access_locked, lock_reason, locked_payment_request_id FROM users WHERE id=?", (user_id,)).fetchone()
    if row and int(row["access_locked"] or 0) == 1:
        return row
    return None


def get_pending_request_for_user(conn: sqlite3.Connection, user_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM debit_payment_requests WHERE user_id=? AND status IN ('Pending','Awaiting Confirmation') ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def mark_paid_awaiting_confirmation(conn: sqlite3.Connection, request_id: int, payer_reference: str = "") -> None:
    conn.execute(
        "UPDATE debit_payment_requests SET status='Awaiting Confirmation', payer_reference=?, paid_at=? WHERE id=?",
        (payer_reference, now_iso(), request_id),
    )
    conn.commit()


def confirm_payment(conn: sqlite3.Connection, request_id: int, confirmed_by: str) -> Tuple[bool, str]:
    req = conn.execute("SELECT * FROM debit_payment_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        return False, "Payment request not found."
    if req["status"] == "Confirmed":
        return True, "Already confirmed."
    bal = funds_balance(conn)
    credit = money(req["total_due"])
    new_bal = money(bal + credit)
    conn.execute(
        "UPDATE debit_payment_requests SET status='Confirmed', confirmed_by=?, confirmed_at=? WHERE id=?",
        (confirmed_by, now_iso(), request_id),
    )
    conn.execute(
        """INSERT INTO business_funds_ledger (entry_time, entry_type, amount, fee_amount, balance_after, related_table, related_id, description, created_by)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (now_iso(), "credit", credit, money(req["fee_amount"]), new_bal, "debit_payment_requests", request_id,
         f"Payment confirmed for {req['username']} ({req['request_code']})", confirmed_by),
    )
    conn.execute(
        "UPDATE users SET access_locked=0, lock_reason=NULL, locked_payment_request_id=NULL WHERE id=?",
        (req["user_id"],),
    )
    conn.commit()
    return True, f"Payment confirmed. Ledger balance: ${new_bal:,.2f}"


def admin_withdraw(conn: sqlite3.Connection, amount: float, method: str, destination: str, created_by: str, notes: str = "") -> Tuple[bool, str]:
    amount = money(amount)
    bal = funds_balance(conn)
    if amount <= 0:
        return False, "Withdrawal amount must be positive."
    if amount > bal:
        return False, f"Insufficient held balance (${bal:,.2f} available)."
    new_bal = money(bal - amount)
    conn.execute(
        """INSERT INTO admin_withdrawals (withdrawal_time, amount, method, destination, status, notes, created_by)
           VALUES (?,?,?,?,?,?,?)""",
        (now_iso(), amount, method, destination, "Completed", notes, created_by),
    )
    wid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO business_funds_ledger (entry_time, entry_type, amount, fee_amount, balance_after, related_table, related_id, description, created_by)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (now_iso(), "debit", -amount, 0, new_bal, "admin_withdrawals", wid, f"Admin withdrawal to {destination}", created_by),
    )
    conn.commit()
    return True, f"Withdrew ${amount:,.2f}. Remaining balance: ${new_bal:,.2f}"


def list_recent_requests(conn: sqlite3.Connection, limit: int = 50) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM debit_payment_requests ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
