# -*- coding: utf-8 -*-
"""Preview a financial CSV (read-only)."""
from __future__ import annotations

from app.office_ai.tools.base import dropbox_records_root

REGISTERS = {
    "payroll_helper": "04_FINANCIAL_TRACKING/Payroll_Helper_Register.csv",
    "income_deposit": "04_FINANCIAL_TRACKING/Income_Deposit_Balance_Register.csv",
    "helper_overhead": "04_FINANCIAL_TRACKING/Helper_Work_Overhead_Register_2026.csv",
    "tax_materials": "04_FINANCIAL_TRACKING/Tax_2026/JRC_Tax_Expenses_Materials_Supplies_2026.csv",
    "owner_labor": "04_FINANCIAL_TRACKING/Tax_2026/JRC_Tax_Owner_Labor_Job_Costing_2026.csv",
}


def run(*, register_key: str = "", tail_lines: int = 15, **kwargs) -> dict:
    if register_key not in REGISTERS:
        return {"ok": False, "error": f"Unknown register. Use: {', '.join(REGISTERS)}"}
    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    path = dr / REGISTERS[register_key]
    if not path.is_file():
        return {"ok": False, "error": f"File missing: {REGISTERS[register_key]}"}
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = lines[-tail_lines:] if tail_lines else lines
    return {
        "ok": True,
        "register": register_key,
        "path": str(path),
        "content": "\n".join(tail)[:16000],
    }


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_financial_register",
        "description": "Read last rows of a financial CSV register (read-only preview).",
        "parameters": {
            "type": "object",
            "properties": {
                "register_key": {"type": "string", "enum": list(REGISTERS.keys())},
                "tail_lines": {"type": "integer"},
            },
            "required": ["register_key"],
        },
    },
}
