# -*- coding: utf-8 -*-
"""Search dropbox-records text files by keyword (read-only)."""
from __future__ import annotations

from app.office_ai.tools.base import dropbox_records_root

_MAX_FILE = 800_000
_ALLOWED_SUFFIX = {".txt", ".csv", ".md", ".json", ".mdc"}


def run(*, query: str = "", limit: int = 8, **kwargs) -> dict:
    if not query or len(query.strip()) < 2:
        return {"ok": False, "error": "query required (min 2 chars)"}
    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    q = query.lower()
    hits = []
    for path in dr.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _ALLOWED_SUFFIX:
            continue
        if path.stat().st_size > _MAX_FILE:
            continue
        rel = str(path.relative_to(dr))
        if q in rel.lower():
            hits.append({"file": rel, "match": "path"})
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if q in text.lower():
            idx = text.lower().find(q)
            start = max(0, idx - 200)
            hits.append({"file": rel, "excerpt": text[start : start + 600]})
        if len(hits) >= limit:
            break
    return {"ok": True, "query": query, "root": str(dr), "hits": hits}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_business_records",
        "description": "Search dropbox-records files by keyword (jobs, logs, standards). Read-only.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}
