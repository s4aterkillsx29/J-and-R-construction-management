# -*- coding: utf-8 -*-
"""Review active users and their roles."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "review_user_permissions",
        "description": "List active users with roles and last login for permission audit.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def run(**kwargs) -> dict:
    from app.network_server import direct_db

    with direct_db() as conn:
        rows = conn.execute(
            "SELECT username, display_name, role, active, last_login, owner_account "
            "FROM users ORDER BY role, username"
        ).fetchall()
    lines = [f"Users ({len(rows)}):"]
    for r in rows:
        owner = " [OWNER]" if int(r["owner_account"] or 0) else ""
        active = "active" if r["active"] else "inactive"
        lines.append(
            f"- {r['username']} ({r['display_name'] or ''}) role={r['role']} {active}{owner} "
            f"last_login={r['last_login'] or 'never'}"
        )
    text = "\n".join(lines)
    return {"ok": True, "users": len(rows), "preview_text": text}
