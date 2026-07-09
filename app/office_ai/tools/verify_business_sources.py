# -*- coding: utf-8 -*-
"""Verify business source paths and security linkage."""
from __future__ import annotations

from app.office_ai.path_security import resolve_office_records, program_repo_root


def run(**kwargs) -> dict:
    dr = resolve_office_records()
    repo = program_repo_root()
    marker = dr / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv" if dr else None
    checks = {
        "dropbox_records_resolved": bool(dr),
        "register_marker_present": bool(marker and marker.is_file()),
        "program_repo_present": bool(repo),
        "path": str(dr) if dr else "",
    }
    ok = checks["dropbox_records_resolved"] and checks["register_marker_present"]
    return {
        "ok": ok,
        "checks": checks,
        "message": "Business sources OK" if ok else "dropbox-records not linked — check Dropbox sync",
    }


SCHEMA = {
    "type": "function",
    "function": {
        "name": "verify_business_sources",
        "description": "Verify dropbox-records is resolved and job register marker exists (security source-of-truth check).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
