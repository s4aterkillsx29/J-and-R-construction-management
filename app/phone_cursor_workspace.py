# -*- coding: utf-8 -*-
"""Deploy phone Cursor files into the unified J&R workspace (00_START_HERE)."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.jrc_workspace import (
    START_HERE,
    WORKSPACE_NAME,
    ensure_unified_workspace,
    resolve_workspace,
    workspace_layout,
    write_workspace_manifest,
)

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = BASE_DIR / "scripts" / "templates" / "dropbox_workspace"

VERIFY_QUOTE_MARKER = "$13,890"
VERIFY_QUOTE_FILE = START_HERE / "JRC-315_LILY_FENCE_QUOTE_CURRENT.txt"


def deploy_templates(workspace: Path) -> List[str]:
    notes: List[str] = []
    if not TEMPLATES.is_dir():
        return [f"templates missing: {TEMPLATES}"]
    workspace_roots = {"02_RECEIPTS_PHOTO_INBOX", "08_Admin_Standards", "06_Bookkeeping_Taxes"}
    for src in TEMPLATES.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(TEMPLATES)
        top = rel.parts[0] if rel.parts else ""
        if top in workspace_roots or top == "00_START_HERE":
            dest = workspace / rel
        else:
            dest = workspace / START_HERE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        notes.append(f"deployed {rel}")
    write_workspace_manifest(workspace)
    guide = workspace.parent / "OPEN_JRC_BUSINESS_HERE.txt"
    guide.write_text(
        "\n".join(
            [
                f"ONE WORKSPACE — open this inner folder in phone Cursor:",
                f"  {workspace}",
                "",
                f"Folder name: {WORKSPACE_NAME}",
                "",
                f"Verify: {START_HERE / 'JRC-315_LILY_FENCE_QUOTE_CURRENT.txt'}",
                f"Expect: {VERIFY_QUOTE_MARKER} Lily Sassafras fence quote",
                "",
                "Do NOT use GitHub for business files.",
            ]
        ),
        encoding="utf-8",
    )
    notes.append("wrote JRC_WORKSPACE.txt + OPEN_JRC_BUSINESS_HERE.txt")
    return notes


def verify_phone_workspace(workspace: Optional[Path] = None) -> Dict[str, Any]:
    root = workspace or resolve_workspace(BASE_DIR)
    layout = workspace_layout(root) if root else {}
    report: Dict[str, Any] = {
        "ok": False,
        "workspace": str(root) if root else None,
        "quote_file": None,
        "quote_has_amount": False,
        "errors": [],
        "notes": [],
    }
    if not root:
        report["errors"].append("Unified workspace not found.")
        return report
    quote = layout.get("start_here", root / START_HERE) / VERIFY_QUOTE_FILE.name
    report["quote_file"] = str(quote)
    if not quote.is_file():
        report["errors"].append(f"Missing: {quote}")
        return report
    text = quote.read_text(encoding="utf-8", errors="replace")
    if VERIFY_QUOTE_MARKER in text and "Lily" in text:
        report["quote_has_amount"] = True
        report["ok"] = True
        report["notes"].append("Unified workspace verify OK.")
    else:
        report["errors"].append("Quote missing $13,890 Lily marker.")
    for rel in (
        START_HERE / "PHONE_CURSOR_DROPBOX_WORKSPACE.txt",
        START_HERE / "READABLE" / "BUSINESS_DASHBOARD.txt",
    ):
        if not (root / rel).is_file():
            report["errors"].append(f"Missing: {rel}")
            report["ok"] = False
    return report


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("--deploy", "deploy"):
        unified = ensure_unified_workspace(BASE_DIR)
        if not unified.get("ok"):
            print(unified.get("errors"))
            return 1
        root = Path(unified["workspace"])
        for n in deploy_templates(root):
            print(n)
        rep = verify_phone_workspace(root)
        print("Verify:", "OK" if rep["ok"] else "FAILED", rep.get("errors"))
        return 0 if rep["ok"] else 1
    if args[0] in ("--verify", "verify"):
        rep = verify_phone_workspace()
        print("OK" if rep["ok"] else "FAIL", rep)
        return 0 if rep["ok"] else 1
    print("Usage: python -m app.phone_cursor_workspace [--deploy | --verify]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
