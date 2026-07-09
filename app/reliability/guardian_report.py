# -*- coding: utf-8 -*-
"""Copy Guardian reports to exports/ and Dropbox 07_ program folder."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def save_report(base_dir: Path, name: str, content: str, detail: Dict[str, Any] | None = None) -> Path:
    from app.program_paths import program_docs_dir

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    exports = base_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    local_path = exports / f"JRC_Guardian_{name}_{ts}.txt"
    local_path.write_text(content, encoding="utf-8")
    try:
        docs = program_docs_dir()
        dest_dir = docs / "exports"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / local_path.name).write_text(content, encoding="utf-8")
    except Exception:
        pass
    return local_path
