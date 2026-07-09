# -*- coding: utf-8 -*-
"""Read JRC job relation register CSV."""
from __future__ import annotations

from app.office_ai.tools.base import dropbox_records_root


def run(**kwargs) -> dict:
    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    path = dr / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
    if not path.is_file():
        return {"ok": False, "error": "Job register CSV missing"}
    return {"ok": True, "path": str(path), "content": path.read_text(encoding="utf-8", errors="ignore")[:20000]}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_job_register",
        "description": "Read JRC_JOB_RELATION_REGISTER.csv for job codes and customer names.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
