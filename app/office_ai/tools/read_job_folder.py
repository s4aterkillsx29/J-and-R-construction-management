# -*- coding: utf-8 -*-
"""Summarize a job folder listing."""
from __future__ import annotations

from app.office_ai.tools.base import find_job_folder


def run(*, job_code: str = "", **kwargs) -> dict:
    if not job_code:
        return {"ok": False, "error": "job_code required"}
    folder = find_job_folder(job_code)
    if not folder:
        return {"ok": False, "error": f"No folder found for {job_code}"}
    lines = [f"Job folder: {folder}"]
    for sub in sorted(folder.iterdir()):
        if sub.is_dir():
            count = sum(1 for _ in sub.rglob("*") if _.is_file())
            lines.append(f"  {sub.name}/ ({count} files)")
        elif sub.is_file():
            lines.append(f"  {sub.name}")
    for name in ("Internal_Workup", "internal_summary", "job_summary"):
        for p in folder.rglob(f"*{name}*"):
            if p.is_file() and p.suffix.lower() in {".txt", ".md"}:
                lines.append(f"\n--- {p.name} (excerpt) ---\n{p.read_text(encoding='utf-8', errors='ignore')[:4000]}")
                break
    return {"ok": True, "job_code": job_code, "content": "\n".join(lines)[:16000]}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_job_folder",
        "description": "List and summarize a job folder by JRC code (e.g. JRC-315).",
        "parameters": {
            "type": "object",
            "properties": {"job_code": {"type": "string", "description": "JRC job code"}},
            "required": ["job_code"],
        },
    },
}
