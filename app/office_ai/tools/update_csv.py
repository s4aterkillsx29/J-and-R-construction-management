# -*- coding: utf-8 -*-
"""Preview financial CSV update — execution requires owner approval."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from app.office_ai.tools.base import dropbox_records_root

MONEY_CSVS = {
    "payroll_helper": "04_FINANCIAL_TRACKING/Payroll_Helper_Register.csv",
    "income_deposit": "04_FINANCIAL_TRACKING/Income_Deposit_Balance_Register.csv",
    "tax_materials": "04_FINANCIAL_TRACKING/Tax_2026/JRC_Tax_Expenses_Materials_Supplies_2026.csv",
    "helper_overhead": "04_FINANCIAL_TRACKING/Helper_Work_Overhead_Register_2026.csv",
}


def preview(*, csv_key: str = "", row_json: str = "", **kwargs) -> dict:
    if csv_key not in MONEY_CSVS:
        return {"ok": False, "error": f"Unknown csv_key. Use one of: {', '.join(MONEY_CSVS)}"}
    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    rel = MONEY_CSVS[csv_key]
    path = dr / rel.replace("/", "\\").replace("\\", "/")
    path = dr / Path(rel)
    if not path.is_file():
        return {"ok": False, "error": f"CSV not found: {rel}"}
    preview_text = f"Would append row to {rel}:\n{row_json}\n\nExisting file: {path}\n"
    try:
        tail = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-5:]
        preview_text += "Last lines:\n" + "\n".join(tail)
    except Exception:
        pass
    return {
        "ok": True,
        "csv_key": csv_key,
        "relative_path": rel,
        "row_json": row_json,
        "preview_text": preview_text,
        "path": str(path),
    }


def execute(*, csv_key: str = "", row_json: str = "", **kwargs) -> dict:
    info = preview(csv_key=csv_key, row_json=row_json)
    if not info.get("ok"):
        return info
    path = Path(info["path"])
    import json

    try:
        row = json.loads(row_json) if row_json.strip().startswith("{") else {"note": row_json}
    except Exception:
        row = {"note": row_json}
    fieldnames = list(row.keys())
    if path.stat().st_size > 0:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                fieldnames = reader.fieldnames
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return {"ok": True, "path": str(path), "message": "CSV row appended after approval"}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_financial_csv",
        "description": "Propose appending a row to a financial CSV (requires owner approval before write).",
        "parameters": {
            "type": "object",
            "properties": {
                "csv_key": {
                    "type": "string",
                    "enum": list(MONEY_CSVS.keys()),
                    "description": "Which register to update",
                },
                "row_json": {"type": "string", "description": "JSON object of column values"},
            },
            "required": ["csv_key", "row_json"],
        },
    },
}
