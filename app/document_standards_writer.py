# -*- coding: utf-8 -*-
"""Open customer documents to JRC standards (LibreOffice Writer or default editor)."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

TEMPLATE_MAP = {
    "invoice": "JR_Construction_Customer_Invoice_Template.txt",
    "estimate": "JR_Construction_Customer_Invoice_Template.txt",
    "internal_workup": "JR_Construction_Internal_Workup_Template.txt",
    "daily_log": "JR_Construction_Daily_Job_Log_Template.txt",
}


def _find_workspace_templates() -> Optional[Path]:
    for candidate in (
        Path(__file__).resolve().parents[2] / "local-office" / "04_Operations_Templates",
        Path.home() / "projects" / "JRC-Construction-Office" / "local-office" / "04_Operations_Templates",
    ):
        if candidate.is_dir():
            return candidate
    return None


def ensure_document_templates(base_dir: Path) -> Path:
    """Sync text/PDF templates into program folder."""
    dest = base_dir / "document_templates"
    dest.mkdir(parents=True, exist_ok=True)
    src = _find_workspace_templates()
    if src:
        for name in TEMPLATE_MAP.values():
            p = src / name
            if p.is_file():
                shutil.copy2(p, dest / name)
        for pdf in src.glob("JR_Construction_*.pdf"):
            shutil.copy2(pdf, dest / pdf.name)
    standards_note = dest / "JRC_Document_Standards_Readme.txt"
    if not standards_note.is_file():
        standards_note.write_text(
            "J & R Construction — document standards\n"
            "Header: J & R Construction | (910) 712-0936 | date/time\n"
            "Default terms: 50% deposit / 50% balance (70/30 material-heavy jobs)\n"
            "No internal costs on customer documents.\n"
            "Full spec: dropbox-records/08_Admin_Standards/DOCUMENT_GENERATION_STANDARDS.txt\n",
            encoding="utf-8",
        )
    return dest


def _find_libreoffice() -> Optional[Path]:
    for path in (
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "LibreOffice" / "program" / "soffice.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "LibreOffice" / "program" / "soffice.exe",
    ):
        if path.is_file():
            return path
    return None


def create_draft(base_dir: Path, doc_type: str = "invoice", job_slug: str = "") -> Tuple[Path, str]:
    templates = ensure_document_templates(base_dir)
    key = doc_type.strip().lower().replace(" ", "_")
    tpl_name = TEMPLATE_MAP.get(key, TEMPLATE_MAP["invoice"])
    src = templates / tpl_name
    if not src.is_file():
        src = templates / "JRC_Document_Standards_Readme.txt"
    drafts = base_dir / "exports" / "document_drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")
    slug = job_slug.replace(" ", "_")[:40] if job_slug else "Draft"
    dest = drafts / f"{stamp}__JRC__{slug}__{key}__Draft.txt"
    if dest.is_file():
        dest = drafts / f"{stamp}__JRC__{slug}__{key}__Draft_{time.strftime('%H%M%S')}.txt"
    shutil.copy2(src, dest)
    return dest, f"Draft created: {dest.name}"


def open_draft_for_editing(path: Path) -> Tuple[bool, str]:
    path = Path(path)
    if not path.is_file():
        return False, f"File not found: {path}"
    lo = _find_libreoffice()
    try:
        if lo:
            subprocess.Popen(
                [str(lo), "--writer", str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, f"Opened in LibreOffice Writer: {path.name}"
        os.startfile(str(path))  # type: ignore[attr-defined]
        return True, f"Opened with default editor: {path.name}"
    except Exception as exc:
        return False, str(exc)


def launch_standards_document(base_dir: Path, doc_type: str = "invoice", job_slug: str = "") -> Tuple[bool, str]:
    path, msg = create_draft(base_dir, doc_type, job_slug)
    ok, open_msg = open_draft_for_editing(path)
    return ok, f"{msg}\n{open_msg}"
