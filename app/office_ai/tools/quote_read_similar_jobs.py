# -*- coding: utf-8 -*-
"""Find similar jobs from register by customer or job type."""
from __future__ import annotations

import csv

SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_similar_jobs",
        "description": "Search job register for similar jobs by slug, customer, or status.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Customer name, job slug, or keyword"},
            },
            "required": ["query"],
        },
    },
}


def run(*, query: str, **kwargs) -> dict:
    from app.office_ai.tools.base import dropbox_records_root

    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    reg = dr / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
    if not reg.is_file():
        return {"ok": False, "error": "Job register not found"}
    q = (query or "").lower()
    hits = []
    with reg.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            blob = " ".join(str(v) for v in row.values()).lower()
            if q in blob:
                hits.append(row)
    lines = [f"Similar jobs for '{query}' ({len(hits)}):"]
    for row in hits[:15]:
        code = row.get("Job_Code") or row.get("job_code") or "?"
        slug = row.get("Job_Slug") or row.get("job_slug") or row.get("Folder_Name") or ""
        lines.append(f"  • {code} — {slug}")
    text = "\n".join(lines) if hits else f"No register matches for '{query}'."
    return {"ok": True, "matches": len(hits), "preview_text": text}
