# -*- coding: utf-8 -*-
"""Audit currently active online sessions."""
from __future__ import annotations

import datetime as dt

SCHEMA = {
    "type": "function",
    "function": {
        "name": "audit_active_sessions",
        "description": "List active online sessions with IP, device, and last seen.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def run(**kwargs) -> dict:
    from app.network_server import direct_db

    from app.network_server import SESSION_TIMEOUT_MINUTES

    cutoff = (dt.datetime.now() - dt.timedelta(minutes=SESSION_TIMEOUT_MINUTES)).isoformat(timespec="seconds")
    with direct_db() as conn:
        rows = conn.execute(
            "SELECT username, role, ip_address, client_device_label, login_time, last_seen "
            "FROM online_sessions WHERE active=1 AND revoked=0 AND last_seen >= ? "
            "ORDER BY last_seen DESC",
            (cutoff,),
        ).fetchall()
    if not rows:
        text = f"No active sessions in the last {SESSION_TIMEOUT_MINUTES} minutes."
    else:
        lines = [f"Active sessions ({len(rows)}):"]
        for r in rows:
            lines.append(
                f"- {r['username']} ({r['role']}) ip={r['ip_address'] or ''} "
                f"device={r['client_device_label'] or 'Unknown'} last_seen={r['last_seen'] or ''}"
            )
        text = "\n".join(lines)
    return {"ok": True, "session_count": len(rows), "preview_text": text}
