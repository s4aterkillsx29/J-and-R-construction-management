# -*- coding: utf-8 -*-
"""Draft quote scope from job folder files (suggest tier)."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "draft_quote_scope",
        "description": "Draft customer-facing scope lines from job folder notes and workup.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_code": {"type": "string"},
                "doc_type": {"type": "string", "enum": ["quote", "proposal", "invoice"], "default": "quote"},
            },
            "required": ["job_code"],
        },
    },
}


def run(*, job_code: str, doc_type: str = "quote", **kwargs) -> dict:
    from app.office_ai.tools.base import find_job_folder

    folder = find_job_folder(job_code)
    if not folder:
        return {"ok": False, "error": f"Job folder not found for {job_code}"}
    scope_files = list(folder.glob("*Scope*")) + list(folder.glob("*scope*")) + list(folder.glob("*Internal_Workup*"))
    parts = [f"Draft {doc_type} scope for {job_code} — {folder.name}", ""]
    if scope_files:
        for sf in scope_files[:3]:
            parts.append(f"--- From {sf.name} ---")
            parts.append(sf.read_text(encoding="utf-8", errors="ignore")[:4000])
    else:
        parts.append("(No scope/workup files found — add scope notes in job folder first.)")
    if doc_type == "proposal":
        parts.append("\n[Proposal mode: scope only — no pricing on customer doc]")
    text = "\n".join(parts)
    return {"ok": True, "doc_type": doc_type, "preview_text": text[:8000]}
