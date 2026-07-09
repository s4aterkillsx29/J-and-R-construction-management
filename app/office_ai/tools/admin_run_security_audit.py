# -*- coding: utf-8 -*-
"""Run read-only security audit summary."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_security_audit",
        "description": "Summarize recent security events and file access policy status.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def run(**kwargs) -> dict:
    from app.network_server import direct_db

    parts = ["=== Security Audit Summary ==="]
    with direct_db() as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='security_events'"
        ).fetchone()
        if table:
            events = conn.execute(
                "SELECT event_type, username, detail, severity, created_at "
                "FROM security_events ORDER BY id DESC LIMIT 15"
            ).fetchall()
            parts.append(f"Recent security events ({len(events)}):")
            for e in events:
                parts.append(
                    f"- [{e['severity'] or 'INFO'}] {e['event_type']} user={e['username'] or ''} "
                    f"{(e['detail'] or '')[:120]} ({e['created_at'] or ''})"
                )
        else:
            parts.append("No security_events table yet.")
        blocked = conn.execute(
            "SELECT COUNT(*) FROM users WHERE active=0"
        ).fetchone()[0]
        parts.append(f"Inactive/blocked user accounts: {blocked}")
    try:
        from app import file_access_security as fas

        parts.append("File access security module: loaded")
        if hasattr(fas, "audit_summary"):
            parts.append(str(fas.audit_summary()))
    except Exception as exc:
        parts.append(f"File access module note: {exc}")
    text = "\n".join(parts)
    return {"ok": True, "preview_text": text}
