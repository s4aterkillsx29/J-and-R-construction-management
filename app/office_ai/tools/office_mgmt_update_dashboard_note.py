# -*- coding: utf-8 -*-
"""Preview a BUSINESS_DASHBOARD section update (approval required to write)."""
from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_dashboard_note",
        "description": "Preview updating a section of BUSINESS_DASHBOARD.txt.",
        "parameters": {
            "type": "object",
            "properties": {
                "section": {"type": "string", "description": "Section heading to update"},
                "content": {"type": "string", "description": "New content for that section"},
            },
            "required": ["section", "content"],
        },
    },
}


def preview(*, section: str, content: str, **kwargs) -> dict:
    return run(section=section, content=content, **kwargs)


def run(*, section: str, content: str, **kwargs) -> dict:
    from app.office_ai.tools.base import readable_path

    p = readable_path("BUSINESS_DASHBOARD.txt")
    if not p:
        return {"ok": False, "error": "BUSINESS_DASHBOARD.txt not found"}
    current = p.read_text(encoding="utf-8", errors="ignore")[:2000]
    text = (
        f"Dashboard update preview\n"
        f"Section: {section.strip()}\n"
        f"New content:\n{content.strip()}\n\n"
        f"Current file excerpt:\n{current}\n\n"
        f"Requires owner approval before write."
    )
    return {"ok": True, "preview_text": text}
