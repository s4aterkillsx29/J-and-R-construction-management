# -*- coding: utf-8 -*-
"""Read internal workup for a job (internal numbers only)."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_internal_workup",
        "description": "Read *__Internal_Workup__* file from job folder — internal costing only.",
        "parameters": {
            "type": "object",
            "properties": {"job_code": {"type": "string", "description": "JRC-### code"}},
            "required": ["job_code"],
        },
    },
}


def run(*, job_code: str, **kwargs) -> dict:
    from app.office_ai.tools.base import find_job_folder

    folder = find_job_folder(job_code)
    if not folder:
        return {"ok": False, "error": f"Job folder not found for {job_code}"}
    matches = list(folder.glob("*Internal_Workup*"))
    if not matches:
        return {"ok": False, "error": f"No internal workup in {folder.name}"}
    text = matches[0].read_text(encoding="utf-8", errors="ignore")[:12000]
    return {"ok": True, "file": matches[0].name, "workup": text, "preview_text": text[:8000]}
