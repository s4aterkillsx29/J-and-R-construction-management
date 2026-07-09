# -*- coding: utf-8 -*-
"""Run workspace sync (approval required)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _sync_script() -> Path | None:
    for candidate in (
        Path.home() / "projects" / "JRC-Construction-Office" / "tools" / "Log-WorkspaceSync.ps1",
        Path(__file__).resolve().parents[3] / "tools" / "Log-WorkspaceSync.ps1",
    ):
        if candidate.is_file():
            return candidate
    return None


def preview(**kwargs) -> dict:
    script = _sync_script()
    if not script:
        return {"ok": False, "error": "Log-WorkspaceSync.ps1 not found"}
    preview_text = (
        f"Would run workspace sync:\n  {script}\n\n"
        "This refreshes readable reports, syncs Dropbox folders, and updates business indexes."
    )
    return {"ok": True, "preview_text": preview_text, "script": str(script)}


def execute(**kwargs) -> dict:
    script = _sync_script()
    if not script:
        return {"ok": False, "error": "Log-WorkspaceSync.ps1 not found"}
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(script.parent.parent),
        )
        out = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-500:]
        if proc.returncode != 0:
            return {"ok": False, "error": f"Sync exit {proc.returncode}", "output": out}
        return {"ok": True, "message": "Workspace sync completed", "output": out}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run(**kwargs) -> dict:
    return preview(**kwargs)


SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_workspace_sync",
        "description": "Run Log-WorkspaceSync.ps1 to refresh readable reports and sync Dropbox (requires owner approval).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
