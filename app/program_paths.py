# -*- coding: utf-8 -*-
"""Program vs business path separation — single resolver for v8."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = BASE_DIR / "PROGRAM_BUSINESS_MANIFEST.json"


def program_root() -> Path:
    """Install directory (program code + runtime DB)."""
    hint = os.environ.get("JRC_INSTALL_DIR", "").strip()
    if hint:
        return Path(hint).resolve()
    return BASE_DIR.resolve()


def business_root() -> Optional[Path]:
    """dropbox-records folder when available locally."""
    from app.dropbox_workspace import resolve_dropbox_records

    return resolve_dropbox_records(BASE_DIR)


def tools_root() -> Path:
    """Office scripts (PDF builder, sync) — workspace tools/, not app runtime."""
    return (BASE_DIR.parent / "tools").resolve()


def load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.is_file():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def assert_program_path(path: Path | str) -> Path:
    """Raise if path is outside program install or contains forbidden business segments."""
    p = Path(path).resolve()
    root = program_root()
    if not _is_under(p, root):
        raise ValueError(f"Not a program path: {p} (expected under {root})")
    manifest = load_manifest()
    text = str(p).replace("\\", "/")
    for segment in manifest.get("forbidden_in_program", []):
        seg = str(segment).replace("\\", "/")
        if seg in text:
            raise ValueError(f"Forbidden business segment '{segment}' in program path: {p}")
    return p


def assert_business_path(path: Path | str) -> Path:
    """Raise if path is not under dropbox-records or approved tools/."""
    p = Path(path).resolve()
    biz = business_root()
    if biz and _is_under(p, biz):
        return p
    tr = tools_root()
    if tr.is_dir() and _is_under(p, tr):
        return p
    raise ValueError(f"Not a business/tools path: {p}")


def assert_bridge_allowed(bridge_name: str) -> None:
    manifest = load_manifest()
    bridges = manifest.get("approved_bridges") or {}
    if bridge_name not in bridges:
        raise ValueError(f"Bridge not approved: {bridge_name}")


def program_docs_dir() -> Path:
    """07_JRC_MANAGER_PROGRAM_FILES — program documentation mirror in Dropbox."""
    biz = business_root()
    if biz:
        return biz / "07_JRC_MANAGER_PROGRAM_FILES"
    return BASE_DIR / "exports" / "program_docs"


def classify_path(path: Path | str) -> str:
    """Return program | business | tools | unknown."""
    p = Path(path).resolve()
    if _is_under(p, program_root()):
        return "program"
    biz = business_root()
    if biz and _is_under(p, biz):
        return "business"
    tr = tools_root()
    if tr.is_dir() and _is_under(p, tr):
        return "tools"
    return "unknown"
