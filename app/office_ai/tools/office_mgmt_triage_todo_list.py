# -*- coding: utf-8 -*-
"""Group CURRENT_TO_DO items by urgency."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "triage_todo_list",
        "description": "Read CURRENT_TO_DO and group items by urgency (today, this week, later).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def run(**kwargs) -> dict:
    from app.office_ai.tools.base import readable_path

    p = readable_path("CURRENT_TO_DO.txt")
    if not p:
        return {"ok": False, "error": "CURRENT_TO_DO.txt not found in readable reports"}
    text = p.read_text(encoding="utf-8", errors="ignore")
    urgent, week, later = [], [], []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        low = s.lower()
        if any(k in low for k in ("urgent", "today", "asap", "!!!", "overdue")):
            urgent.append(s)
        elif any(k in low for k in ("week", "soon", "follow up", "call")):
            week.append(s)
        else:
            later.append(s)
    out = ["=== To-Do Triage ===", f"Urgent ({len(urgent)}):"]
    out.extend(f"  • {x}" for x in urgent[:20])
    out.append(f"This week ({len(week)}):")
    out.extend(f"  • {x}" for x in week[:20])
    out.append(f"Later ({len(later)}):")
    out.extend(f"  • {x}" for x in later[:20])
    summary = "\n".join(out)
    return {"ok": True, "urgent": len(urgent), "this_week": len(week), "later": len(later), "preview_text": summary}
