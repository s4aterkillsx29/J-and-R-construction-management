# -*- coding: utf-8 -*-
"""Read-only consistency audit via Office AI."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_consistency_audit",
        "description": "Compare job register, payroll/income CSVs, sync timestamps vs program DB (read-only).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def run(**kwargs) -> dict:
    from app.reliability.consistency_audit import format_report, run_read_only_audit

    rep = run_read_only_audit()
    text = format_report(rep)
    return {"ok": True, "report": rep, "preview_text": text}
