# -*- coding: utf-8 -*-
"""Search chatgpt_imports folder by keyword."""
from __future__ import annotations

import os
from pathlib import Path


def run(*, query: str = "", limit: int = 10, **kwargs) -> dict:
    if not query:
        return {"ok": False, "error": "query required"}
    base = Path(os.environ.get("JRC_CHATGPT_IMPORTS_DIR", "")).expanduser()
    if not base.is_dir():
        base = Path(__file__).resolve().parents[2] / "chatgpt_imports"
    if not base.is_dir():
        return {"ok": False, "error": "chatgpt_imports folder not found"}
    q = query.lower()
    hits = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".txt", ".md", ".json", ".csv"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if q in text.lower() or q in path.name.lower():
            hits.append({"file": str(path), "excerpt": text[:1500]})
        if len(hits) >= limit:
            break
    return {"ok": True, "query": query, "hits": hits}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_chatgpt_imports",
        "description": "Search exported ChatGPT files in chatgpt_imports for keywords.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max files to return"},
            },
            "required": ["query"],
        },
    },
}
