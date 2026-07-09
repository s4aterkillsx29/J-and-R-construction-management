# -*- coding: utf-8 -*-
"""Office AI path security — writes only under verified dropbox-records."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Set

_BLOCKED_NAME_PARTS = frozenset({
    ".env", "credentials", "password", "secret", "api_key", "jr_business.db",
})

_READ_ONLY_PROGRAM_DIRS = frozenset({"app", "scripts", "docs", "tools"})


def resolve_office_records() -> Optional[Path]:
    try:
        from app.dropbox_workspace import resolve_dropbox_records

        return resolve_dropbox_records()
    except Exception:
        return None


def path_under_office_records(path: Path) -> bool:
    root = resolve_office_records()
    if not root:
        return False
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def is_blocked_filename(name: str) -> bool:
    lower = (name or "").lower()
    return any(part in lower for part in _BLOCKED_NAME_PARTS)


def assert_office_write_path(path: Path) -> Optional[str]:
    if is_blocked_filename(path.name):
        return f"Blocked filename pattern: {path.name}"
    if not path_under_office_records(path):
        return f"Write path must be under dropbox-records: {path}"
    return None


def program_repo_root() -> Optional[Path]:
    base = Path(__file__).resolve().parents[2]
    if (base / "app" / "network_server.py").is_file():
        return base
    return None


def assert_program_read_path(path: Path) -> Optional[str]:
    root = program_repo_root()
    if not root:
        return "Program repo not found"
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        return "Path outside program repo"
    if rel.parts and rel.parts[0] not in _READ_ONLY_PROGRAM_DIRS:
        return f"Read limited to {', '.join(sorted(_READ_ONLY_PROGRAM_DIRS))}/"
    if path.suffix.lower() not in {".py", ".txt", ".md", ".mdc", ".json", ".ps1", ".bat"}:
        return "File type not allowed for program read"
    if is_blocked_filename(path.name):
        return "Blocked file pattern"
    return None
