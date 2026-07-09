# -*- coding: utf-8 -*-
"""Read business dashboard readable file."""
from __future__ import annotations

from app.office_ai.tools.base import dropbox_records_root


def run(**kwargs) -> dict:
    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found on this PC"}
    path = dr / "00_START_HERE" / "READABLE" / "BUSINESS_DASHBOARD.txt"
    if not path.is_file():
        return {"ok": False, "error": f"Missing {path.name}"}
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {"ok": True, "path": str(path), "content": text[:16000]}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_dashboard",
        "description": "Read the plain-English BUSINESS_DASHBOARD.txt for money, jobs, and to-do.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
