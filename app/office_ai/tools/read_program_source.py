# -*- coding: utf-8 -*-
"""Read program source file (read-only, admin)."""
from __future__ import annotations

from pathlib import Path

from app.office_ai.path_security import assert_program_read_path, program_repo_root

_MAX = 80000


def run(*, relative_path: str = "", **kwargs) -> dict:
    if not relative_path:
        return {"ok": False, "error": "relative_path required e.g. app/network_server.py"}
    root = program_repo_root()
    if not root:
        return {"ok": False, "error": "Program repo not found"}
    rel = relative_path.replace("\\", "/").lstrip("/")
    path = (root / rel).resolve()
    err = assert_program_read_path(path)
    if err:
        return {"ok": False, "error": err}
    if not path.is_file():
        return {"ok": False, "error": f"Not found: {rel}"}
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) > _MAX:
        text = text[: _MAX // 2] + "\n\n[... truncated ...]\n\n" + text[-_MAX // 2 :]
    return {"ok": True, "path": rel, "content": text}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_program_source",
        "description": "Read a source file from app/, scripts/, docs/, or tools/ for coding help (read-only).",
        "parameters": {
            "type": "object",
            "properties": {
                "relative_path": {"type": "string", "description": "e.g. app/office_ai/orchestrator.py"},
            },
            "required": ["relative_path"],
        },
    },
}
