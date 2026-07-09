# -*- coding: utf-8 -*-
"""Program structure summary for advanced coding assistance."""
from __future__ import annotations

from app.office_ai.path_security import program_repo_root


def run(**kwargs) -> dict:
    root = program_repo_root()
    if not root:
        return {"ok": False, "error": "Program repo not found"}
    lines = [
        f"Program root: {root}",
        "Key entry points:",
        "  app/start_center.py — Start Center desktop hub",
        "  app/network_server.py — Flask web/mobile host",
        "  app/jr_job_manager.py — Desktop business UI",
        "  app/office_ai/ — In-app Office AI (admin only)",
        "  app/file_access_security.py — Role file guards",
        "  app/dropbox_workspace.py — dropbox-records resolution",
        "Security: configure_ai permission admin-only; money CSV writes need approval.",
        "Business source of truth: dropbox-records/ (not chat).",
    ]
    for name in ("VERSION.txt", "requirements.txt", "PHASE_VERIFICATION_REPORT.txt"):
        p = root / name
        if p.is_file():
            lines.append(f"{name}: {p.read_text(encoding='utf-8', errors='ignore')[:200].strip()}")
    return {"ok": True, "content": "\n".join(lines)}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_program_structure",
        "description": "Summarize JRC Manager program layout, entry points, and security model for coding tasks.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
