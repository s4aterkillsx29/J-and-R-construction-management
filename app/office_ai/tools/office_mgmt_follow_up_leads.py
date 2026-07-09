# -*- coding: utf-8 -*-
"""Find leads/estimates with no response in 7+ days."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

SCHEMA = {
    "type": "function",
    "function": {
        "name": "follow_up_leads",
        "description": "List Leads_Estimates job folders older than 7 days for follow-up.",
        "parameters": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Minimum age in days", "default": 7}},
            "required": [],
        },
    },
}


def run(*, days: int = 7, **kwargs) -> dict:
    from app.office_ai.tools.base import dropbox_records_root

    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    leads = dr / "01_Jobs" / "Leads_Estimates"
    if not leads.is_dir():
        return {"ok": False, "error": "Leads_Estimates folder not found"}
    cutoff = dt.datetime.now() - dt.timedelta(days=max(1, int(days)))
    stale = []
    for folder in sorted(leads.iterdir()):
        if not folder.is_dir():
            continue
        mtime = dt.datetime.fromtimestamp(folder.stat().st_mtime)
        if mtime < cutoff:
            stale.append((folder.name, mtime.strftime("%Y-%m-%d")))
    lines = [f"Leads needing follow-up (>{days} days, {len(stale)}):"]
    for name, when in stale[:30]:
        lines.append(f"  • {name} (last folder activity {when})")
    text = "\n".join(lines) if stale else f"No leads older than {days} days in Leads_Estimates."
    return {"ok": True, "count": len(stale), "preview_text": text}
