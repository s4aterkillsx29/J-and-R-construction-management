# -*- coding: utf-8 -*-
"""Append timestamped note to today's daily log."""
from __future__ import annotations

import datetime as dt

from app.office_ai.path_security import assert_office_write_path
from app.office_ai.tools.base import daily_log_path


def run(*, note: str = "", **kwargs) -> dict:
    if not note or not note.strip():
        return {"ok": False, "error": "note required"}
    path = daily_log_path()
    if not path:
        return {"ok": False, "error": "Could not resolve daily log path"}
    err = assert_office_write_path(path)
    if err:
        return {"ok": False, "error": err}
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n[{ts} Office AI]\n{note.strip()}\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="ignore")
        path.write_text(existing + entry, encoding="utf-8")
    else:
        header = f"J & R Construction Daily Log — {dt.date.today().isoformat()}\n{'=' * 60}\n"
        path.write_text(header + entry, encoding="utf-8")
    return {"ok": True, "path": str(path), "message": "Daily log updated"}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "append_daily_log",
        "description": "Append a timestamped note to today's daily log in dropbox-records (auto-approved).",
        "parameters": {
            "type": "object",
            "properties": {"note": {"type": "string", "description": "Log entry text"}},
            "required": ["note"],
        },
    },
}
