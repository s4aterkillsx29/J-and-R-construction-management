# -*- coding: utf-8 -*-
"""Save a receipt note to the business receipts inbox."""
from __future__ import annotations

import datetime as dt

from app.office_ai.path_security import assert_office_write_path
from app.office_ai.tools.base import dropbox_records_root


def _receipts_inbox() -> "Path | None":
    from pathlib import Path

    dr = dropbox_records_root()
    if not dr:
        return None
    inbox = dr / "03_BUSINESS_ADMIN" / "Receipts_Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


def run(*, note: str = "", job_code: str = "", amount: str = "", **kwargs) -> dict:
    if not note or not note.strip():
        return {"ok": False, "error": "note required"}
    inbox = _receipts_inbox()
    if not inbox:
        return {"ok": False, "error": "dropbox-records receipts inbox not found"}
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_job = (job_code or "general").strip().replace("/", "-").replace("\\", "-")[:40]
    path = inbox / f"{ts}__{safe_job}__receipt_note.txt"
    err = assert_office_write_path(path)
    if err:
        return {"ok": False, "error": err}
    lines = [
        "J & R Construction — Receipt Note",
        f"Saved: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Job: {job_code or 'General'}",
        f"Amount: {amount or 'n/a'}",
        "",
        note.strip(),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "path": str(path), "preview_text": f"Saved receipt note to {path.name}"}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "save_receipt_note",
        "description": "Save a receipt/expense note into the business receipts inbox (auto-approved).",
        "parameters": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "Receipt note text"},
                "job_code": {"type": "string", "description": "Optional job code"},
                "amount": {"type": "string", "description": "Optional amount"},
            },
            "required": ["note"],
        },
    },
}
