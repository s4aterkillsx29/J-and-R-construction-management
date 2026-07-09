# -*- coding: utf-8 -*-
"""Repair tier policy — AUTO / APPROVAL / BLOCKED."""
from __future__ import annotations

from typing import Literal

Tier = Literal["AUTO", "APPROVAL", "BLOCKED"]

_AUTO = frozenset(
    {
        "venv_check",
        "launcher_check",
        "folder_check",
        "wal_checkpoint",
        "host_ping",
        "troubleshooter_safe",
        "deps_check",
    }
)

_APPROVAL = frozenset(
    {
        "csv_merge",
        "financial_write",
        "workspace_sync",
        "pdf_generate",
        "code_patch",
        "schema_migration",
    }
)


def repair_tier(action: str) -> Tier:
    key = (action or "").strip().lower()
    if key in _AUTO:
        return "AUTO"
    if key in _APPROVAL:
        return "APPROVAL"
    if key.startswith("csv") or key.startswith("financial"):
        return "APPROVAL"
    return "BLOCKED"


def can_auto_repair(action: str, *, auto_repair_enabled: bool) -> bool:
    if not auto_repair_enabled:
        return False
    return repair_tier(action) == "AUTO"
