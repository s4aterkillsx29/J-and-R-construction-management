# -*- coding: utf-8 -*-
"""Read a named file from 08_Admin_Standards."""
from __future__ import annotations

from app.office_ai.tools.base import standards_path


def run(*, filename: str = "", **kwargs) -> dict:
    if not filename:
        return {"ok": False, "error": "filename required (e.g. DOCUMENT_GENERATION_STANDARDS.txt)"}
    name = filename.replace("\\", "/").split("/")[-1]
    path = standards_path(name)
    if not path:
        return {"ok": False, "error": f"Standards file not found: {name}"}
    return {"ok": True, "path": str(path), "content": path.read_text(encoding="utf-8", errors="ignore")[:20000]}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_standards_file",
        "description": "Read a file from dropbox-records/08_Admin_Standards/ by filename.",
        "parameters": {
            "type": "object",
            "properties": {"filename": {"type": "string"}},
            "required": ["filename"],
        },
    },
}
