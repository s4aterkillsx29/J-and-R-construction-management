# -*- coding: utf-8 -*-
"""Draft a structured log entry from natural language (preview only)."""
from __future__ import annotations

import datetime as dt

SCHEMA = {
    "type": "function",
    "function": {
        "name": "draft_log_entry",
        "description": "Convert natural language note into a structured daily log entry preview.",
        "parameters": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "What happened — payment, materials, helper, etc."},
                "job_code": {"type": "string", "description": "Optional JRC-### code"},
            },
            "required": ["note"],
        },
    },
}


def preview(*, note: str, job_code: str = "", **kwargs) -> dict:
    return run(note=note, job_code=job_code, **kwargs)


def run(*, note: str, job_code: str = "", **kwargs) -> dict:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    code = (job_code or "").strip().upper()
    draft = [
        f"J & R Construction — Daily Log Draft",
        f"Date/Time: {now}",
        f"Job: {code or 'General / Admin'}",
        "",
        "Event:",
        note.strip(),
        "",
        "Suggested follow-up CSVs (owner confirms before write):",
        "- Income_Deposit_Balance_Register.csv (if payment)",
        "- JRC_Tax_Expenses_Materials_Supplies_2026.csv (if receipt)",
        "- Payroll_Helper_Register.csv + Helper_Work_Overhead_Register_2026.csv (if helper paid)",
        "- Tax_Savings_Tracker_2026.csv (mandatory on payment)",
    ]
    text = "\n".join(draft)
    return {"ok": True, "draft": text, "preview_text": text}
