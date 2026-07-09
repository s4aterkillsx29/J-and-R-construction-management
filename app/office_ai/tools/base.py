# -*- coding: utf-8 -*-
"""Shared paths for office AI tools — canonical dropbox-records via dropbox_workspace."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

from app.office_ai.path_security import resolve_office_records


def dropbox_records_root() -> Optional[Path]:
    root = resolve_office_records()
    if root and root.is_dir():
        return root
    # Fallback: project junction
    repo = Path(__file__).resolve().parents[2]
    for candidate in (
        repo.parent / "dropbox-records",
        Path.home() / "projects" / "JRC-Construction-Office" / "dropbox-records",
    ):
        marker = candidate / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
        if marker.is_file():
            return candidate.resolve()
    return None


def standards_path(name: str) -> Optional[Path]:
    dr = dropbox_records_root()
    if not dr:
        return None
    p = dr / "08_Admin_Standards" / name
    return p if p.is_file() else None


def readable_path(name: str) -> Optional[Path]:
    dr = dropbox_records_root()
    if not dr:
        return None
    p = dr / "00_START_HERE" / "READABLE" / name
    return p if p.is_file() else None


def daily_log_path() -> Optional[Path]:
    dr = dropbox_records_root()
    if not dr:
        return None
    log_dir = dr / "03_BUSINESS_ADMIN" / "Daily_Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    existing = sorted(log_dir.glob(f"{today}*.txt"), reverse=True)
    if existing:
        return existing[0]
    return log_dir / f"{today}__JR_Construction_Daily_Log.txt"


def find_job_folder(job_code: str) -> Optional[Path]:
    dr = dropbox_records_root()
    if not dr:
        return None
    code = job_code.strip().upper()
    if not code.startswith("JRC-"):
        code = f"JRC-{code.replace('JRC', '').strip('-')}"
    jobs_root = dr / "01_Jobs"
    if not jobs_root.is_dir():
        return None
    for sub in ("Active", "Completed", "Leads_Estimates"):
        base = jobs_root / sub
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            if folder.is_dir() and code.replace("-", "") in folder.name.replace("-", "").upper():
                return folder
            if folder.is_dir() and code in folder.name.upper():
                return folder
    return None
