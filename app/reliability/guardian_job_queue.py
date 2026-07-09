# -*- coding: utf-8 -*-
"""Serialize Guardian + sync + pipeline jobs — one heavy job at a time."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from app.reliability import guardian_store

_lock = threading.Lock()
_busy = False


def enqueue(conn, job_type: str, payload: Optional[Dict[str, Any]] = None) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO guardian_job_queue (queued_at, job_type, payload_json, status) VALUES (?,?,?,?)",
        (now, job_type, json.dumps(payload or {}), "pending"),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def run_next(conn, runner: Callable[[str, dict], dict]) -> Optional[dict]:
    """Run one pending job if queue not busy."""
    global _busy
    with _lock:
        if _busy:
            return {"ok": False, "skipped": True, "reason": "queue_busy"}
        row = conn.execute(
            "SELECT * FROM guardian_job_queue WHERE status='pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            return None
        _busy = True
        job_id = row["id"]
        job_type = row["job_type"]
        payload = json.loads(row["payload_json"] or "{}")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE guardian_job_queue SET status='running', started_at=? WHERE id=?",
            (now, job_id),
        )
        conn.commit()
    try:
        result = runner(job_type, payload)
        status = "done" if result.get("ok", True) else "failed"
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        status = "failed"
    finally:
        with _lock:
            _busy = False
        fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE guardian_job_queue SET status=?, finished_at=?, result_json=? WHERE id=?",
            (status, fin, json.dumps(result), job_id),
        )
        conn.commit()
    return result
