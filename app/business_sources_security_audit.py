# -*- coding: utf-8 -*-
"""Verify business sources linked to program security and Office AI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
APP = BASE / "app"
errors: list[str] = []
notes: list[str] = []


def check(name: str, ok: bool, fail: str = "") -> None:
    if ok:
        notes.append(f"OK: {name}")
    else:
        errors.append(fail or name)


def main() -> int:
    from app.dropbox_workspace import resolve_dropbox_records
    from app.office_ai.path_security import program_repo_root, resolve_office_records
    from app.office_ai.tool_registry import _TOOL_MODULES, tool_schemas
    from app.file_access_security import verify_file_access_security

    dr = resolve_dropbox_records()
    check("dropbox_workspace.resolve_dropbox_records", dr is not None and dr.is_dir())
    if dr:
        marker = dr / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
        check("JRC_JOB_RELATION_REGISTER.csv present", marker.is_file())

    check("office_ai path_security.resolve_office_records", resolve_office_records() is not None)

    cfg_path = APP / "office_ai" / "office_ai_sources.json"
    if cfg_path.is_file():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        check("office_ai_sources business_source_policy", "business_source_policy" in cfg)
        for tier in ("core", "session", "task", "security", "developer"):
            check(f"tier {tier} defined", tier in cfg.get("tiers", {}))

    check("office_ai tools count >= 18", len(_TOOL_MODULES) >= 18)
    check("tool schemas count", len(tool_schemas()) >= 18)
    for required in (
        "verify_business_sources",
        "read_security_policies",
        "search_business_records",
        "read_program_source",
        "list_program_modules",
        "run_workspace_sync",
        "generate_customer_pdf",
    ):
        check(f"tool {required}", required in _TOOL_MODULES)

    from app.office_ai import approval_gate

    for tool in ("update_financial_csv", "run_workspace_sync", "generate_customer_pdf"):
        check(f"approval required {tool}", approval_gate.requires_approval(tool))

    ok_fas = verify_file_access_security() == 0
    check("file_access_security", ok_fas)

    ns = (APP / "network_server.py").read_text(encoding="utf-8", errors="ignore")
    check("register_office_ai_routes", "register_office_ai_routes" in ns)
    check("configure_ai permission gating", "configure_ai" in (APP / "role_permissions.py").read_text(encoding="utf-8"))

    repo = program_repo_root()
    check("program repo for dev tools", repo is not None)

    # Live tool smoke
    from app.office_ai.tools import verify_business_sources as vbs

    result = vbs.run()
    check("verify_business_sources tool", result.get("ok") is True, str(result))

    print("JRC Business Sources Security Audit")
    print("Errors:", len(errors))
    for e in errors:
        print(" ERROR -", e)
    for n in notes:
        print(" ", n)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
