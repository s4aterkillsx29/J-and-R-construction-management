# -*- coding: utf-8 -*-
"""Compare draft quote files to sent customer documents."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "compare_quote_to_sent",
        "description": "Compare job folder draft vs sent customer invoice/quote files.",
        "parameters": {
            "type": "object",
            "properties": {"job_code": {"type": "string"}},
            "required": ["job_code"],
        },
    },
}


def run(*, job_code: str, **kwargs) -> dict:
    from app.office_ai.tools.base import dropbox_records_root, find_job_folder

    folder = find_job_folder(job_code)
    if not folder:
        return {"ok": False, "error": f"Job folder not found for {job_code}"}
    dr = dropbox_records_root()
    drafts = [p.name for p in folder.glob("*DRAFT*")]
    sent_job = [p.name for p in folder.glob("*Customer*") if "DRAFT" not in p.name.upper()]
    sent_central = []
    if dr:
        inv = dr / "02_Documents_Invoices_Estimates_Quotes"
        if inv.is_dir():
            code = job_code.upper().replace("JRC-", "JRC-")
            sent_central = [p.name for p in inv.glob(f"*{code}*") if p.is_file()][:10]
    lines = [
        f"Quote comparison for {job_code}",
        f"Job folder drafts ({len(drafts)}): {', '.join(drafts[:8]) or 'none'}",
        f"Job folder sent customer docs ({len(sent_job)}): {', '.join(sent_job[:8]) or 'none'}",
        f"Central invoice folder ({len(sent_central)}): {', '.join(sent_central[:8]) or 'none'}",
    ]
    if drafts and not sent_job and not sent_central:
        lines.append("Status: DRAFT ONLY — not yet sent to customer.")
    elif sent_job or sent_central:
        lines.append("Status: Sent customer document exists — do not overwrite without flag.")
    text = "\n".join(lines)
    return {"ok": True, "preview_text": text}
