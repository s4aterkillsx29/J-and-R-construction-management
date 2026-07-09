# -*- coding: utf-8 -*-
"""Review tax savings plan notes and flag missing quarterly actions."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "check_tax_savings_plan",
        "description": "Read the tax savings plan checklist and summarize open items for the owner.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def _candidate_paths():
    from app.office_ai.tools.base import readable_path, standards_path

    names = (
        "TAX_SAVINGS_PLAN.txt",
        "TAX_SAVINGS_CHECKLIST.txt",
        "TAX_PLANNING_NOTES.txt",
    )
    for name in names:
        p = readable_path(name) or standards_path(name)
        if p:
            yield p


def run(**kwargs) -> dict:
    paths = list(_candidate_paths())
    if not paths:
        return {
            "ok": False,
            "error": "Tax savings plan file not found in dropbox-records readable/standards folders",
        }

    path = paths[0]
    text = path.read_text(encoding="utf-8", errors="ignore")
    open_items = []
    done_items = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        low = stripped.lower()
        if stripped.startswith(("- [ ]", "[ ]", "TODO", "todo")) or any(
            k in low for k in ("pending", "need", "review", "follow up", "quarter")
        ):
            open_items.append(stripped)
        elif stripped.startswith(("- [x]", "[x]", "done")):
            done_items.append(stripped)

    lines = [
        "=== Tax Savings Plan Review ===",
        f"Source: {path.name}",
        f"Open items: {len(open_items)}",
        f"Completed items: {len(done_items)}",
    ]
    if open_items:
        lines.append("Needs attention:")
        lines.extend(f"  • {item}" for item in open_items[:25])
    else:
        lines.append("No open checklist items detected. Review file manually for quarterly deadlines.")
    summary = "\n".join(lines)
    return {
        "ok": True,
        "open_items": len(open_items),
        "completed_items": len(done_items),
        "preview_text": summary,
    }
