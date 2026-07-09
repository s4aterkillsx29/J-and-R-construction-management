# -*- coding: utf-8 -*-
"""Summarize pending account requests for admin review."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "summarize_pending_accounts",
        "description": "List pending account requests with username, role, and contact info.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def run(**kwargs) -> dict:
    from app.network_server import direct_db

    with direct_db() as conn:
        rows = conn.execute(
            "SELECT requested_username, display_name, requested_role, email, phone, created_at "
            "FROM account_requests WHERE status='Pending' ORDER BY created_at DESC"
        ).fetchall()
    if not rows:
        text = "No pending account requests."
    else:
        lines = [f"Pending account requests ({len(rows)}):"]
        for r in rows:
            lines.append(
                f"- {r['requested_username']} ({r['display_name'] or 'no name'}) "
                f"role={r['requested_role']} email={r['email'] or ''} phone={r['phone'] or ''} "
                f"submitted={r['created_at'] or ''}"
            )
        text = "\n".join(lines)
    return {"ok": True, "summary": text, "count": len(rows), "preview_text": text}
