# -*- coding: utf-8 -*-
"""Generate morning office brief from dashboard + to-do."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_office_brief",
        "description": "Summarize BUSINESS_DASHBOARD, CURRENT_TO_DO, and cash on hand for Jacob.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def run(**kwargs) -> dict:
    from app.office_ai.tools.base import dropbox_records_root

    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    parts = []
    for rel, label in (
        ("00_START_HERE/READABLE/BUSINESS_DASHBOARD.txt", "Dashboard"),
        ("00_START_HERE/READABLE/CURRENT_TO_DO.txt", "To-do"),
        ("00_START_HERE/READABLE/CASH_ON_HAND_CURRENT.txt", "Cash on hand"),
    ):
        p = dr / rel.replace("/", "\\")
        p = dr / rel
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")[:4000]
            parts.append(f"=== {label} ===\n{text}")
    brief = "\n\n".join(parts) if parts else "No readable reports found. Run workspace sync."
    return {"ok": True, "brief": brief, "preview_text": brief[:8000]}
