# -*- coding: utf-8
"""Read LOGGING_EVENT_CHECKLIST.txt."""
from __future__ import annotations

from app.office_ai.tools.base import dropbox_records_root


def run(**kwargs) -> dict:
    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    path = dr / "00_START_HERE" / "LOGGING_EVENT_CHECKLIST.txt"
    if not path.is_file():
        return {"ok": False, "error": "Logging checklist missing"}
    return {"ok": True, "path": str(path), "content": path.read_text(encoding="utf-8", errors="ignore")[:20000]}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_logging_checklist",
        "description": "Read the master LOGGING_EVENT_CHECKLIST for what CSVs and files to update per event.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
