# -*- coding: utf-8 -*-
"""List JRC Manager app modules (developer overview)."""
from __future__ import annotations

from app.office_ai.path_security import program_repo_root


def run(**kwargs) -> dict:
    root = program_repo_root()
    if not root:
        return {"ok": False, "error": "Program repo not found"}
    app_dir = root / "app"
    modules = sorted(p.name for p in app_dir.glob("*.py") if p.is_file())
    packages = sorted(p.name for p in app_dir.iterdir() if p.is_dir() and not p.name.startswith("_"))
    dev_start = root / "JRC_MANAGER_DEV_START.txt"
    dev_note = dev_start.read_text(encoding="utf-8", errors="ignore")[:4000] if dev_start.is_file() else ""
    return {
        "ok": True,
        "repo": str(root),
        "app_modules": modules[:80],
        "app_packages": packages,
        "dev_start_excerpt": dev_note,
    }


SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_program_modules",
        "description": "List JRC Manager Python modules and packages for programming/debug context (read-only).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
