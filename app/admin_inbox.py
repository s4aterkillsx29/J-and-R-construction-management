# -*- coding: utf-8 -*-
"""Aggregate pending admin inbox counts."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parents[1]


def _db_path(base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir or BASE_DIR)
    data = Path(os.environ.get("JRC_DATA_DIR", str(root / "data"))).expanduser()
    return Path(os.environ.get("JRC_DB_PATH", str(data / "jr_business.db"))).expanduser()


def _connect(base_dir: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(base_dir), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _count(conn: sqlite3.Connection, sql: str, default: int = 0) -> int:
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else default
    except Exception:
        return default


def aggregate_inbox(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    counts: Dict[str, int] = {
        "pending_logins": 0,
        "worker_applications": 0,
        "ai_approvals": 0,
        "densus_pending": 0,
        "payment_requests": 0,
        "host_running": 0,
    }
    try:
        from app.server_control import get_status

        st = get_status(base_dir)
        counts["host_running"] = 1 if st.get("running") else 0
    except Exception:
        pass

    try:
        with _connect(base_dir) as conn:
            counts["pending_logins"] = _count(
                conn,
                "SELECT COUNT(*) FROM account_requests WHERE status='Pending'",
            )
            counts["ai_approvals"] = _count(
                conn,
                "SELECT COUNT(*) FROM office_ai_pending_actions WHERE status='Pending'",
            )
            counts["densus_pending"] = _count(
                conn,
                """SELECT COUNT(*) FROM densus_access_requests
                   WHERE COALESCE(status,'Pending')='Pending'""",
            )
            counts["payment_requests"] = _count(
                conn,
                """SELECT COUNT(*) FROM payment_requests
                   WHERE COALESCE(status,'pending') IN ('pending','Pending')""",
            )
            for table in ("worker_applications", "job_applications", "applications"):
                try:
                    n = _count(
                        conn,
                        f"SELECT COUNT(*) FROM {table} WHERE COALESCE(status,'Pending')='Pending'",
                    )
                    if n:
                        counts["worker_applications"] += n
                except Exception:
                    continue
    except Exception:
        pass

    total = sum(v for k, v in counts.items() if k != "host_running")
    return {
        "ok": True,
        "counts": counts,
        "total_pending": total,
    }
