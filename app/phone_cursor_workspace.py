# -*- coding: utf-8 -*-
"""Deploy and verify phone Cursor + Dropbox workspace (00_START_HERE files)."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = BASE_DIR / "scripts" / "templates" / "dropbox_workspace"

VERIFY_QUOTE_MARKER = "$13,890"
VERIFY_QUOTE_FILE = "00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt"


def _business_root_candidates() -> List[Path]:
    from app.dropbox_workspace import business_root_candidates

    return business_root_candidates(BASE_DIR)


def resolve_business_root() -> Optional[Path]:
    from app.dropbox_workspace import resolve_business_root as _resolve

    return _resolve(BASE_DIR)


def deploy_templates(business_root: Path) -> List[str]:
    """Copy phone workspace templates into business_root/00_START_HERE."""
    notes: List[str] = []
    if not TEMPLATES.is_dir():
        notes.append(f"templates missing: {TEMPLATES}")
        return notes
    dest_root = business_root / "00_START_HERE"
    for src in TEMPLATES.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(TEMPLATES)
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        notes.append(f"deployed {rel}")
    guide = business_root.parent / "OPEN_JRC_BUSINESS_HERE.txt"
    guide.write_text(
        "\n".join(
            [
                "Open this folder in Cursor on your PHONE for business work.",
                "",
                f"INNER FOLDER: {business_root}",
                "",
                f"VERIFY: open {VERIFY_QUOTE_FILE}",
                f"You should see the {VERIFY_QUOTE_MARKER} Lily Sassafras fence quote.",
                "",
                "Do NOT use GitHub for business files.",
            ]
        ),
        encoding="utf-8",
    )
    notes.append("wrote OPEN_JRC_BUSINESS_HERE.txt")
    return notes


def verify_phone_workspace(business_root: Optional[Path] = None) -> Dict[str, Any]:
    root = business_root or resolve_business_root()
    report: Dict[str, Any] = {
        "ok": False,
        "business_root": str(root) if root else None,
        "quote_file": None,
        "quote_has_amount": False,
        "errors": [],
        "notes": [],
    }
    if not root:
        report["errors"].append("Dropbox business root not found on this PC.")
        return report
    quote = root / VERIFY_QUOTE_FILE.replace("/", "\\") if "\\" in str(root) else root / VERIFY_QUOTE_FILE
    report["quote_file"] = str(quote)
    if not quote.is_file():
        report["errors"].append(f"Missing verification file: {quote}")
        return report
    text = quote.read_text(encoding="utf-8", errors="replace")
    if VERIFY_QUOTE_MARKER in text and "Lily" in text:
        report["quote_has_amount"] = True
        report["ok"] = True
        report["notes"].append("Phone workspace verify OK — $13,890 Lily quote found.")
    else:
        report["errors"].append("Quote file exists but missing $13,890 Lily marker.")
    for name in (
        "00_START_HERE/PHONE_CURSOR_DROPBOX_WORKSPACE.txt",
        "00_START_HERE/READABLE/BUSINESS_DASHBOARD.txt",
    ):
        p = root / name.replace("/", "\\") if "\\" in str(root) else root / name
        if not p.is_file():
            report["errors"].append(f"Missing bookmark file: {name}")
            report["ok"] = False
    return report


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("--deploy", "deploy"):
        root = resolve_business_root()
        if not root:
            print("Business root not found. Run on office PC with Dropbox synced.")
            print("Or: scripts\\Sync-JRCBusinessFolders.ps1")
            return 1
        notes = deploy_templates(root)
        for n in notes:
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
