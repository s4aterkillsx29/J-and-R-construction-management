# -*- coding: utf-8 -*-
"""Read security and data-isolation policy docs."""
from __future__ import annotations

from app.office_ai.tools.base import dropbox_records_root


def run(**kwargs) -> dict:
    dr = dropbox_records_root()
    if not dr:
        return {"ok": False, "error": "dropbox-records not found"}
    parts = []
    for rel in (
        "07_JRC_MANAGER_PROGRAM_FILES/DATA_ISOLATION_BY_USER_TYPE.txt",
        "08_Admin_Standards/FOLDER_MAINTENANCE_GUIDE.txt",
        "00_START_HERE/LOGGING_STANDARDS_OFFICE_ASSISTANT.txt",
    ):
        path = dr / rel.replace("/", "\\").replace("\\", "/")
        path = dr / rel
        if path.is_file():
            parts.append(f"### {rel}\n{path.read_text(encoding='utf-8', errors='ignore')[:8000]}\n")
    try:
        from app.file_access_security import verify_file_access_security

        ok, notes = verify_file_access_security()
        parts.append(f"### file_access_security static\n{'PASS' if ok else 'FAIL'}\n" + "\n".join(notes[:12]))
    except Exception as exc:
        parts.append(f"### file_access_security\n(check skipped: {exc})\n")
    return {"ok": True, "content": "\n".join(parts)[:24000]}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_security_policies",
        "description": "Read data isolation, logging security, and file access policy summaries.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
