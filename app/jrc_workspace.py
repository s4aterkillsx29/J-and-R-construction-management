# -*- coding: utf-8 -*-
"""Single J&R business workspace — Dropbox root for phone Cursor, office records, and Manager."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()

# ONE workspace folder name (phone Cursor, desktop, and Construction Manager).
WORKSPACE_NAME = "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
WORKSPACE_MARKER = "JRC_WORKSPACE.txt"
REGISTER_REL = Path("08_Admin_Standards") / "JRC_JOB_RELATION_REGISTER.csv"
START_HERE = Path("00_START_HERE")
READABLE = START_HERE / "READABLE"

DEFAULT_INNER_WORKSPACE = Path(
    r"C:\Users\enrag\Dropbox\All Files\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
) / WORKSPACE_NAME
LEGACY_OFFICE_RECORDS = Path(
    r"c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records"
)

_CONFIG_FILE = DATA_DIR / "jrc_workspace.json"


def _home_dropbox() -> Path:
    return Path.home() / "Dropbox"


def _has_register(path: Path) -> bool:
    return (path / REGISTER_REL).is_file()


def _is_workspace_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / WORKSPACE_MARKER).is_file():
        return True
    if _has_register(path):
        return True
    if (path / START_HERE).is_dir():
        return True
    entries = [p for p in path.iterdir() if p.name not in ("README_KEEP.txt", ".jrc_dropbox_mirror")]
    return len(entries) > 0


def workspace_candidates(base_dir: Optional[Path] = None) -> List[Path]:
    """All paths that may be the single business workspace (ordered)."""
    base = base_dir or BASE_DIR
    dropbox = _home_dropbox()
    saved = load_saved_workspace()
    env_paths = [
        os.environ.get("JRC_WORKSPACE_ROOT", "").strip(),
        os.environ.get("JRC_DROPBOX_BUSINESS_ROOT", "").strip(),
        os.environ.get("JRC_DROPBOX_RECORDS", "").strip(),
    ]
    candidates: List[Path] = []
    if saved:
        candidates.append(saved)
    for raw in env_paths:
        if raw:
            candidates.append(Path(raw))
    candidates.extend(
        [
            dropbox / "All Files" / WORKSPACE_NAME / WORKSPACE_NAME,
            dropbox / "All Files" / WORKSPACE_NAME,
            dropbox / WORKSPACE_NAME / WORKSPACE_NAME,
            dropbox / "dropbox-records",
            dropbox / "J and R Construction",
            DEFAULT_INNER_WORKSPACE,
            LEGACY_OFFICE_RECORDS,
            base.parent / "dropbox-records",
            Path(os.environ.get("JRC_DROPBOX_MIRROR", str(BASE_DIR / "dropbox-business"))),
        ]
    )
    seen: set[str] = set()
    unique: List[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def load_saved_workspace() -> Optional[Path]:
    try:
        if _CONFIG_FILE.is_file():
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            root = Path(data.get("workspace_root", ""))
            if root.is_dir():
                return root.resolve()
    except Exception:
        pass
    return None


def save_workspace(root: Path, base_dir: Optional[Path] = None) -> Path:
    """Persist the canonical workspace path and write root marker file."""
    root = root.resolve()
    base = base_dir or BASE_DIR
    data_dir = Path(os.environ.get("JRC_DATA_DIR", str(base / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg = data_dir / "jrc_workspace.json"
    payload = {
        "workspace_root": str(root),
        "workspace_name": WORKSPACE_NAME,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "One Dropbox workspace for phone Cursor, office CSVs, quotes, and Manager.",
    }
    cfg.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_workspace_manifest(root)
    apply_workspace_env(root)
    return root


def write_workspace_manifest(root: Path) -> None:
    manifest = root / WORKSPACE_MARKER
    manifest.write_text(
        "\n".join(
            [
                "J & R CONSTRUCTION — SINGLE BUSINESS WORKSPACE",
                f"Workspace name: {WORKSPACE_NAME}",
                f"Root path: {root}",
                "",
                "Everything lives under THIS folder:",
                "  00_START_HERE/          phone Cursor + quick files",
                "  02_RECEIPTS_PHOTO_INBOX/  iPhone receipt photo drops",
                "  03_BUSINESS_ADMIN/      applications inbox",
                "  04_FINANCIAL_TRACKING/  income and deposits",
                "  05_Helper_Pay_Workers/  payroll",
                "  07_JRC_MANAGER_PROGRAM_FILES/  program backups",
                "  08_Admin_Standards/     job register and standards",
                "",
                "Phone Cursor: open THIS folder only (not GitHub).",
                "Construction Manager: Office Records Sync uses this same root.",
                "",
                "Verify: 00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt ($13,890)",
            ]
        ),
        encoding="utf-8",
    )


def apply_workspace_env(root: Path) -> None:
    """Point all legacy env aliases at the one workspace."""
    s = str(root)
    os.environ["JRC_WORKSPACE_ROOT"] = s
    os.environ["JRC_DROPBOX_BUSINESS_ROOT"] = s
    os.environ["JRC_DROPBOX_RECORDS"] = s


def resolve_workspace(base_dir: Optional[Path] = None, *, save: bool = False) -> Optional[Path]:
    """Return the single J&R business workspace folder."""
    for candidate in workspace_candidates(base_dir):
        if _is_workspace_dir(candidate):
            root = candidate.resolve()
            if save:
                save_workspace(root, base_dir)
            else:
                apply_workspace_env(root)
            return root
    return None


def resolve_dropbox_records(base_dir: Optional[Path] = None) -> Optional[Path]:
    """Alias — office records are the same as the unified workspace."""
    return resolve_workspace(base_dir)


def resolve_business_root(base_dir: Optional[Path] = None) -> Optional[Path]:
    """Alias — business root is the unified workspace."""
    return resolve_workspace(base_dir)


def workspace_layout(root: Path) -> Dict[str, Path]:
    return {
        "root": root,
        "start_here": root / START_HERE,
        "readable": root / READABLE,
        "admin": root / "03_BUSINESS_ADMIN",
        "financial": root / "04_FINANCIAL_TRACKING",
        "payroll": root / "05_Helper_Pay_Workers",
        "program_files": root / "07_JRC_MANAGER_PROGRAM_FILES",
        "standards": root / "08_Admin_Standards",
        "register": root / REGISTER_REL,
    }


def merge_legacy_records_into_workspace(
    workspace: Path, legacy: Path
) -> List[str]:
    """Copy missing office folders from a separate dropbox-records path into workspace."""
    notes: List[str] = []
    if not legacy.is_dir() or legacy.resolve() == workspace.resolve():
        return notes
    import shutil

    for item in legacy.iterdir():
        if item.name.startswith("."):
            continue
        dest = workspace / item.name
        if dest.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, dest)
            notes.append(f"merged folder {item.name}")
        elif item.is_file():
            shutil.copy2(item, dest)
            notes.append(f"merged file {item.name}")
    return notes


def find_legacy_records_source(base_dir: Optional[Path] = None) -> Optional[Path]:
    """Separate dropbox-records folder to merge into unified workspace."""
    base = base_dir or BASE_DIR
    for candidate in (
        LEGACY_OFFICE_RECORDS,
        base.parent / "dropbox-records",
        _home_dropbox() / "dropbox-records",
    ):
        if candidate.is_dir() and _has_register(candidate):
            ws = resolve_workspace(base_dir, save=False)
            if ws and candidate.resolve() != ws.resolve():
                return candidate.resolve()
    return None


def ensure_unified_workspace(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Resolve, merge legacy paths, save config, return status."""
    base = base_dir or BASE_DIR
    report: Dict[str, Any] = {
        "ok": False,
        "workspace": None,
        "merged_from": None,
        "notes": [],
        "errors": [],
    }
    legacy = find_legacy_records_source(base)
    root = resolve_workspace(base, save=False)
    if legacy and not root:
        root = legacy
    if not root:
        report["errors"].append("Business workspace not found. Install Dropbox and sync, or set JRC_WORKSPACE_ROOT.")
        return report
    if legacy:
        merged = merge_legacy_records_into_workspace(root, legacy)
        if merged:
            report["merged_from"] = str(legacy)
            report["notes"].extend(merged)
    save_workspace(root, base)
    report["workspace"] = str(root)
    report["ok"] = True
    report["notes"].append(f"Unified workspace: {root}")
    return report


def format_workspace_report(report: Dict[str, Any]) -> str:
    lines = [
        "J & R Construction — Unified Business Workspace",
        f"OK: {report.get('ok')}",
        f"Workspace: {report.get('workspace') or 'NOT FOUND'}",
    ]
    if report.get("merged_from"):
        lines.append(f"Merged from: {report['merged_from']}")
    for n in report.get("notes") or []:
        lines.append(f"  - {n}")
    for e in report.get("errors") or []:
        lines.append(f"ERROR: {e}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    base = Path(args[0]) if args and not args[0].startswith("-") else BASE_DIR
    if args and not args[0].startswith("-"):
        args = args[1:]
    cmd = args[0] if args else "--ensure"
    if cmd in ("--ensure", "ensure"):
        rep = ensure_unified_workspace(base)
        print(format_workspace_report(rep))
        return 0 if rep["ok"] else 1
    if cmd in ("--show", "show"):
        root = resolve_workspace(base)
        print(root or "NOT FOUND")
        return 0 if root else 1
    print("Usage: python -m app.jrc_workspace [--ensure | --show]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
