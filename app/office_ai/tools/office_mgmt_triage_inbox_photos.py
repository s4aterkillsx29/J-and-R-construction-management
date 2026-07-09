# -*- coding: utf-8 -*-
"""Suggest job codes for unidentified inbox photos."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "triage_inbox_photos",
        "description": "Scan Dropbox account roots for recent uploads and suggest job assignment.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def run(**kwargs) -> dict:
    import csv
    from pathlib import Path

    from app.office_ai.tools.base import dropbox_records_root

    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    register = dr / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
    codes = []
    if register.is_file():
        with register.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                c = (row.get("Job_Code") or row.get("job_code") or "").strip()
                if c:
                    codes.append(c)
    inbox_dirs = [
        Path.home() / "Dropbox",
        Path.home() / "Dropbox" / "All Files",
    ]
    recent = []
    for root in inbox_dirs:
        if not root.is_dir():
            continue
        for p in sorted(root.glob("*.jpg"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
            recent.append(p.name)
        for p in sorted(root.glob("*.jpeg"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
            recent.append(p.name)
        for p in sorted(root.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
            recent.append(p.name)
    recent = list(dict.fromkeys(recent))[:10]
    lines = ["=== Inbox Photo Triage ===", f"Active job codes ({len(codes)}): {', '.join(codes[:12])}..."]
    if recent:
        lines.append("Recent uploads at Dropbox root (assign to job folder):")
        for name in recent:
            guess = next((c for c in codes if c.replace("-", "") in name.upper().replace("-", "")), "UNASSIGNED")
            lines.append(f"  • {name} → suggest {guess}")
    else:
        lines.append("No recent image uploads found at Dropbox account root.")
    text = "\n".join(lines)
    return {"ok": True, "preview_text": text}
