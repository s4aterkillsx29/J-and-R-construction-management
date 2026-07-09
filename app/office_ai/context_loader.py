# -*- coding: utf-8 -*-
"""Tiered knowledge loading for Office AI."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Dict, List, Optional

from app.office_ai.path_security import resolve_office_records

_PKG = Path(__file__).resolve().parent
_SOURCES_JSON = _PKG / "office_ai_sources.json"


def _workspace_roots() -> List[Path]:
    roots: List[Path] = []
    dr = resolve_office_records()
    if dr:
        roots.append(dr.parent if dr.name == "dropbox-records" else dr)
        if dr.name == "dropbox-records":
            roots.append(dr.parent)
    repo = _PKG.parents[1]
    office = repo.parent
    if office.name == "JRC-Construction-Office" or (office / "dropbox-records").exists():
        if office not in roots:
            roots.append(office)
    for candidate in (
        Path.home() / "projects" / "JRC-Construction-Office",
        Path.home() / "Dropbox" / "All Files" / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22" / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22",
    ):
        if candidate.exists() and candidate not in roots:
            roots.append(candidate)
    return roots


def _resolve_source(relative: str, *, workspace: bool) -> Optional[Path]:
    rel = relative.replace("\\", "/")
    dr = resolve_office_records()
    if rel.startswith("dropbox-records/") and dr:
        sub = rel[len("dropbox-records/") :]
        path = dr / Path(sub)
        if path.is_file():
            return path
    if workspace:
        for root in _workspace_roots():
            path = root / Path(rel)
            if path.is_file():
                return path
    else:
        path = Path(rel)
        if path.is_file():
            return path
    if dr and not rel.startswith("dropbox-records/"):
        path = dr / rel
        if path.is_file():
            return path
    return None


def _read_tail(path: Path, max_chars: int = 12000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars // 2] + "\n\n[... truncated ...]\n\n" + text[-max_chars // 2 :]


def _load_sources_config() -> dict:
    if _SOURCES_JSON.exists():
        return json.loads(_SOURCES_JSON.read_text(encoding="utf-8"))
    return {"tiers": {"core": [], "session": [], "task": {}}}


def load_context(*, tiers: Optional[List[str]] = None, max_total_chars: int = 48000) -> str:
    """Load tiered office context for system prompt."""
    tiers = tiers or ["core", "session", "security"]
    cfg = _load_sources_config()
    tier_defs: Dict[str, list] = cfg.get("tiers", {})
    parts: List[str] = []
    used = 0

    dr = resolve_office_records()
    if dr:
        parts.append(f"### Business source (verified)\ndropbox-records: {dr}\n")
        used += len(parts[-1])

    for tier in tiers:
        for item in tier_defs.get(tier, []):
            rel = item.get("relative", "")
            path = _resolve_source(rel, workspace=bool(item.get("workspace", True)))
            if not path:
                continue
            chunk = _read_tail(path, max_chars=min(10000, max_total_chars - used))
            if not chunk.strip():
                continue
            label = item.get("label", path.name)
            block = f"### {label} ({path.name})\n{chunk}\n"
            if used + len(block) > max_total_chars:
                break
            parts.append(block)
            used += len(block)

    if "session" in tiers and dr:
        today = dt.date.today().isoformat()
        log_dir = dr / "03_BUSINESS_ADMIN" / "Daily_Logs"
        if log_dir.is_dir():
            matches = sorted(log_dir.glob(f"{today}*.txt"), reverse=True)
            if not matches:
                matches = sorted(log_dir.glob("*.txt"), reverse=True)[:1]
            for log_path in matches[:1]:
                tail = _read_tail(log_path, max_chars=4000)
                if tail:
                    parts.append(f"### Today daily log tail ({log_path.name})\n{tail}\n")

    if not parts:
        parts.append(
            "### Office AI\nDropbox office files not found on this PC. "
            "Use verify_business_sources tool. Read-only until dropbox-records path is available.\n"
        )
    return "\n".join(parts)
