# -*- coding: utf-8 -*-
"""Preview a role change proposal (requires owner approval to apply)."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "propose_access_change",
        "description": "Preview changing a user's role. Queued for owner approval — never auto-applies.",
        "parameters": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "new_role": {"type": "string", "description": "Target role (not admin for non-owner)"},
            },
            "required": ["username", "new_role"],
        },
    },
}


def preview(*, username: str, new_role: str, **kwargs) -> dict:
    return run(username=username, new_role=new_role, **kwargs)


def run(*, username: str, new_role: str, **kwargs) -> dict:
    from app.network_server import DEFAULT_ADMIN_USERNAME, direct_db
    from app.role_permissions import normalize_role_for_session

    username = (username or "").strip()
    new_role = normalize_role_for_session(new_role or "viewer")
    with direct_db() as conn:
        row = conn.execute(
            "SELECT username, role, owner_account FROM users WHERE username=?", (username,)
        ).fetchone()
    if not row:
        return {"ok": False, "error": f"User not found: {username}"}
    if int(row["owner_account"] or 0) or row["username"] == DEFAULT_ADMIN_USERNAME:
        return {"ok": False, "error": "Owner account role cannot be changed via AI proposal."}
    if new_role == "admin":
        return {"ok": False, "error": "AI cannot propose admin role — owner must assign manually."}
    old = normalize_role_for_session(row["role"] or "viewer")
    text = (
        f"Proposed access change:\n"
        f"  User: {username}\n"
        f"  Current role: {old}\n"
        f"  Proposed role: {new_role}\n"
        f"Requires owner approval at /office-ai/approvals"
    )
    return {"ok": True, "username": username, "old_role": old, "new_role": new_role, "preview_text": text}
