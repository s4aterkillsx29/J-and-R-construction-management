# -*- coding: utf-8 -*-
"""Host boot / reconnect hook — drain mobile outbox."""
from __future__ import annotations

from pathlib import Path


def on_host_online(base_dir: Path | None = None) -> dict:
    from app.mobile_platform.outbox_schema import ensure_outbox_schema
    from app.mobile_platform.outbox_processor import process_pending
    from app.reliability.guardian_store import connect

    base = base_dir or Path(__file__).resolve().parents[2]
    conn = connect()
    try:
        ensure_outbox_schema(conn)
        return process_pending(conn, base)
    finally:
        conn.close()
