# -*- coding: utf-8 -*-
"""Suggest a role for a pending account request (read-only recommendation)."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "recommend_account_role",
        "description": "Recommend an appropriate role for a pending account request username.",
        "parameters": {
            "type": "object",
            "properties": {"username": {"type": "string", "description": "Requested username"}},
            "required": ["username"],
        },
    },
}


def run(*, username: str, **kwargs) -> dict:
    from app.network_server import direct_db

    username = (username or "").strip()
    with direct_db() as conn:
        row = conn.execute(
            "SELECT requested_role, display_name, notes FROM account_requests "
            "WHERE requested_username=? AND status='Pending' ORDER BY id DESC LIMIT 1",
            (username,),
        ).fetchone()
    if not row:
        return {"ok": False, "error": f"No pending request for {username}"}
    requested = (row["requested_role"] or "guest").lower()
    allowed = {"worker", "helper", "subcontractor", "viewer", "guest", "non_company", "customer"}
    if requested not in allowed:
        recommended = "viewer"
        reason = f"Requested role '{requested}' is not self-service; default to viewer pending owner review."
    else:
        recommended = requested
        reason = f"Requested role '{requested}' matches standard hire/customer roles."
    text = f"User: {username}\nRequested: {requested}\nRecommended: {recommended}\nReason: {reason}"
    return {"ok": True, "recommended_role": recommended, "preview_text": text}
