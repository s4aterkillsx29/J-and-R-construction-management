# -*- coding: utf-8 -*-
"""Resolve J&R business workspace from local Dropbox sync or Dropbox API (cloud agents)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]

# Local mirror for cloud agents when using Dropbox API (gitignored).
CLOUD_MIRROR_DIR = Path(
    os.environ.get("JRC_DROPBOX_MIRROR", str(BASE_DIR / "dropbox-business"))
).expanduser()

REGISTER_MARKER = Path("08_Admin_Standards") / "JRC_JOB_RELATION_REGISTER.csv"

# Owner primary business root (Windows office PC).
DEFAULT_BUSINESS_ROOT = Path(
    r"C:\Users\enrag\Dropbox\All Files\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
    r"\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
)
DEFAULT_OFFICE_RECORDS = Path(
    r"c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records"
)


def _home_dropbox() -> Path:
    return Path.home() / "Dropbox"


def business_root_candidates(base_dir: Optional[Path] = None) -> List[Path]:
    """Ordered local paths that may hold the main J&R business folder."""
    base = base_dir or BASE_DIR
    home = Path.home()
    dropbox = _home_dropbox()
    env_root = os.environ.get("JRC_DROPBOX_BUSINESS_ROOT", "").strip()
    candidates: List[Path] = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(
        [
            CLOUD_MIRROR_DIR,
            dropbox
            / "All Files"
            / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
            / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22",
            dropbox / "J and R Construction",
            dropbox / "JRC",
            dropbox / "Invoices2026 1.0",
            dropbox / "dropbox-records",
            home / "Dropbox (Personal)" / "J and R Construction",
            DEFAULT_BUSINESS_ROOT,
            base.parent / "dropbox-records",
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


def dropbox_records_candidates(base_dir: Optional[Path] = None) -> List[Path]:
    """Ordered local paths for office dropbox-records (Office Assistant source of truth)."""
    base = base_dir or BASE_DIR
    env = os.environ.get("JRC_DROPBOX_RECORDS", "").strip()
    dropbox = _home_dropbox()
    candidates: List[Path] = []
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            CLOUD_MIRROR_DIR / "dropbox-records",
            CLOUD_MIRROR_DIR,
            DEFAULT_OFFICE_RECORDS,
            base.parent / "dropbox-records",
            dropbox / "dropbox-records",
            dropbox
            / "All Files"
            / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
            / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22",
            DEFAULT_BUSINESS_ROOT,
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


def _has_register(path: Path) -> bool:
    return (path / REGISTER_MARKER).is_file()


def resolve_dropbox_records(base_dir: Optional[Path] = None) -> Optional[Path]:
    """Return dropbox-records folder if present locally (synced or mirrored)."""
    for candidate in dropbox_records_candidates(base_dir):
        if _has_register(candidate):
            return candidate.resolve()
    return None


def _is_populated_business_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if _has_register(path):
        return True
    marker = path / ".jrc_dropbox_mirror"
    if marker.is_file():
        return True
    # Ignore placeholder mirror with only README_KEEP.txt
    entries = [p for p in path.iterdir() if p.name != "README_KEEP.txt"]
    return len(entries) > 0


def resolve_business_root(base_dir: Optional[Path] = None) -> Optional[Path]:
    """Return the main business workspace folder when available locally."""
    records = resolve_dropbox_records(base_dir)
    if records:
        # Phone Cursor workspace uses 00_START_HERE beside dropbox-records in cloud mirror.
        parent = records.parent
        if (parent / "00_START_HERE").is_dir():
            return parent.resolve()
        return records
    for candidate in business_root_candidates(base_dir):
        if _is_populated_business_dir(candidate):
            return candidate.resolve()
    return None


def get_dropbox_access_token() -> str:
    return (
        os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip()
        or os.environ.get("JRC_DROPBOX_ACCESS_TOKEN", "").strip()
    )


def get_api_root() -> str:
    """Dropbox API path prefix, e.g. /dropbox-records or empty for account root."""
    root = os.environ.get("DROPBOX_API_ROOT", "").strip()
    if root and not root.startswith("/"):
        root = "/" + root
    return root.rstrip("/")


def access_mode() -> str:
    if resolve_business_root():
        return "local"
    if get_dropbox_access_token():
        return "api"
    return "none"


def _api_json(endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    token = get_dropbox_access_token()
    if not token:
        raise RuntimeError("DROPBOX_ACCESS_TOKEN is not set.")
    url = f"https://api.dropboxapi.com/2/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(payload if payload is not None else None).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dropbox API {endpoint} failed ({exc.code}): {detail}") from exc


def api_account_check() -> Dict[str, Any]:
    return _api_json("users/get_current_account")


def api_search(query: str, *, limit: int = 25) -> List[Dict[str, Any]]:
    root = get_api_root()
    options: Dict[str, Any] = {
        "path": root if root else "",
        "max_results": min(max(limit, 1), 100),
        "file_status": "active",
    }
    payload = {"query": query, "options": options}
    data = _api_json("files/search_v2", payload)
    matches: List[Dict[str, Any]] = []
    for entry in data.get("matches") or []:
        meta = (entry.get("metadata") or {}).get("metadata") or {}
        if meta.get(".tag") == "file":
            matches.append(
                {
                    "name": meta.get("name", ""),
                    "path": meta.get("path_display", ""),
                    "size": meta.get("size", 0),
                    "modified": meta.get("client_modified") or meta.get("server_modified"),
                }
            )
    return matches


def api_upload_file(local_path: Path, dropbox_path: str) -> None:
    """Upload one local file to Dropbox (overwrite). Requires DROPBOX_ACCESS_TOKEN."""
    token = get_dropbox_access_token()
    if not token:
        raise RuntimeError("DROPBOX_ACCESS_TOKEN is not set.")
    content = local_path.read_bytes()
    api_arg = json.dumps(
        {
            "path": dropbox_path,
            "mode": "overwrite",
            "autorename": False,
            "mute": True,
        }
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "Dropbox-API-Arg": api_arg,
    }
    req = urllib.request.Request(
        "https://content.dropboxapi.com/2/files/upload",
        data=content,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dropbox upload failed ({exc.code}): {detail}") from exc


def push_mirror_to_live_dropbox() -> List[str]:
    """Push local mirror files to live Dropbox via API (phone/cloud log update sync)."""
    token = get_dropbox_access_token()
    if not token:
        return ["No DROPBOX_ACCESS_TOKEN — live Dropbox upload skipped (mirror + git only)."]
    prefix = get_api_root().rstrip("/")
    notes: List[str] = []
    roots = [
        CLOUD_MIRROR_DIR / "dropbox-records",
        CLOUD_MIRROR_DIR / "00_START_HERE",
        CLOUD_MIRROR_DIR / "evidence",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for local in root.rglob("*"):
            if not local.is_file():
                continue
            rel = local.relative_to(CLOUD_MIRROR_DIR).as_posix()
            db_path = f"{prefix}/{rel}" if prefix else f"/{rel}"
            try:
                api_upload_file(local, db_path)
                notes.append(f"uploaded to Dropbox: {rel}")
            except Exception as exc:
                notes.append(f"upload failed {rel}: {exc}")
    return notes


PHONE_SESSION_CRITICAL = [
    ("dropbox-records/06_bookkeeping/Owner_Draws_Register.csv", "Non-working business day"),
    ("dropbox-records/06_bookkeeping/Owner_Draws_Register.csv", "Saturday business day"),
    ("dropbox-records/05_Helper_Pay_Workers/Payroll_Helper_Register.csv", "Wayne"),
    ("dropbox-records/08_Admin_Standards/JRC_JOB_RELATION_REGISTER.csv", "Closed Paid"),
    ("dropbox-records/04_FINANCIAL_TRACKING/Income_Deposits_Balances/Income_Deposit_Balance_Register.csv", "5565"),
    ("dropbox-records/07_Personal_Finances/Personal_Income_Register.csv", "340"),
    ("00_START_HERE/PHONE_FIELD_LOG_PASTE.txt", "PHONE FIELD LOG"),
    ("00_START_HERE/READABLE/OWNER_DRAWS_REGISTER.txt", "TOTAL: $870"),
    ("00_START_HERE/READABLE/OFFICE_WORK_QUEUE.txt", "JRC-403"),
    ("00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt", "10,440"),
]


def verify_phone_session_files() -> Dict[str, Any]:
    """Verify this phone session's critical files exist in the mirror with expected content."""
    report: Dict[str, Any] = {"ok": True, "checks": [], "missing": [], "errors": []}
    for rel, marker in PHONE_SESSION_CRITICAL:
        path = CLOUD_MIRROR_DIR / rel
        entry = {"file": rel, "marker": marker, "ok": False}
        if not path.is_file():
            entry["error"] = "missing"
            report["missing"].append(rel)
            report["ok"] = False
        else:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if marker in text:
                    entry["ok"] = True
                else:
                    entry["error"] = f"marker '{marker}' not found"
                    report["ok"] = False
            except OSError as exc:
                entry["error"] = str(exc)
                report["ok"] = False
        report["checks"].append(entry)
    return report


def api_download(dropbox_path: str) -> bytes:
    payload = {"path": dropbox_path}
    token = get_dropbox_access_token()
    if not token:
        raise RuntimeError("DROPBOX_ACCESS_TOKEN is not set.")
    url = "https://content.dropboxapi.com/2/files/download"
    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps(payload),
    }
    req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dropbox download failed ({exc.code}): {detail}") from exc


def mirror_file(dropbox_path: str, local_path: Optional[Path] = None) -> Path:
    """Download one Dropbox file into the local cloud mirror."""
    content = api_download(dropbox_path)
    if local_path is None:
        root = get_api_root().lstrip("/")
        rel = dropbox_path.lstrip("/")
        if root and rel.startswith(root):
            rel = rel[len(root) :].lstrip("/")
        local_path = CLOUD_MIRROR_DIR / rel
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    (CLOUD_MIRROR_DIR / ".jrc_dropbox_mirror").write_text("api\n", encoding="utf-8")
    return local_path


def check_access(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Report how this environment can reach the J&R Dropbox business workspace."""
    base = base_dir or BASE_DIR
    report: Dict[str, Any] = {
        "mode": access_mode(),
        "business_root": None,
        "dropbox_records": None,
        "mirror_dir": str(CLOUD_MIRROR_DIR),
        "candidates_checked": [],
        "api_account": None,
        "errors": [],
        "notes": [
            "GitHub stores application source only — business files live in Dropbox.",
            "Set DROPBOX_ACCESS_TOKEN in Cursor agent secrets for cloud Dropbox API access.",
        ],
    }
    for path in business_root_candidates(base):
        exists = path.is_dir()
        has_reg = _has_register(path) if exists else False
        report["candidates_checked"].append(
            {"path": str(path), "exists": exists, "has_job_register": has_reg}
        )
    root = resolve_business_root(base)
    records = resolve_dropbox_records(base)
    if root:
        report["business_root"] = str(root)
    if records:
        report["dropbox_records"] = str(records)
    token = get_dropbox_access_token()
    if token:
        try:
            acct = api_account_check()
            report["api_account"] = {
                "name": acct.get("name", {}).get("display_name"),
                "email": acct.get("email"),
                "root": get_api_root() or "/",
            }
            if report["mode"] == "api":
                report["notes"].append("Using Dropbox API — search and download available.")
        except Exception as exc:
            report["errors"].append(f"Dropbox API token invalid or unreachable: {exc}")
    elif report["mode"] == "none":
        report["errors"].append(
            "No local Dropbox sync and no DROPBOX_ACCESS_TOKEN. "
            "Install Dropbox on this PC or add a Dropbox API token to agent secrets."
        )
    return report


def api_list_folder(dropbox_path: str, *, recursive: bool = False) -> List[Dict[str, Any]]:
    """List files/folders at a Dropbox path."""
    payload: Dict[str, Any] = {"path": dropbox_path or "", "recursive": recursive}
    data = _api_json("files/list_folder", payload)
    entries = list(data.get("entries") or [])
    while data.get("has_more"):
        data = _api_json("files/list_folder/continue", {"cursor": data["cursor"]})
        entries.extend(data.get("entries") or [])
    return entries


def _mirror_rel_path(dropbox_path: str) -> Path:
    root = get_api_root().lstrip("/")
    rel = dropbox_path.lstrip("/")
    if root and rel.startswith(root):
        rel = rel[len(root) :].lstrip("/")
    return CLOUD_MIRROR_DIR / rel


def sync_file_from_api(dropbox_path: str) -> Optional[Path]:
    """Download one Dropbox file into the local mirror. Returns local path or None on failure."""
    try:
        return mirror_file(dropbox_path)
    except Exception:
        return None


OFFICE_SYNC_PATHS = [
    "08_Admin_Standards/JRC_JOB_RELATION_REGISTER.csv",
    "05_Helper_Pay_Workers/Payroll_Helper_Register.csv",
    "04_FINANCIAL_TRACKING/Income_Deposits_Balances/Income_Deposit_Balance_Register.csv",
    "06_bookkeeping/Owner_Draws_Register.csv",
    "04_FINANCIAL_TRACKING/Business_Account_Balances.csv",
    "04_FINANCIAL_TRACKING/Setaside_Review/Setaside_Review_2026-07-04.csv",
    "04_FINANCIAL_TRACKING/Setaside_Review/Setaside_Transfers_Register.csv",
    "07_Personal_Finances/Personal_Expenses_Register.csv",
    "07_Personal_Finances/Personal_Income_Register.csv",
    "07_Personal_Finances/Personal_Account_Balances.csv",
    "04_FINANCIAL_TRACKING/Cash_Envelope_Status.csv",
]


def _push_templates_to_mirror(base_dir: Path, *, overwrite: bool = True) -> List[str]:
    """Copy repo dropbox_workspace templates into cloud mirror (log + sync pipeline)."""
    import shutil

    notes: List[str] = []
    templates = base_dir / "scripts" / "templates" / "dropbox_workspace"
    if not templates.is_dir():
        notes.append(f"templates missing: {templates}")
        return notes

    records_dest = CLOUD_MIRROR_DIR / "dropbox-records"
    evidence_dest = CLOUD_MIRROR_DIR / "evidence"
    records_skip_in_start = {
        "08_Admin_Standards",
        "05_Helper_Pay_Workers",
        "04_FINANCIAL_TRACKING",
        "06_bookkeeping",
        "07_Personal_Finances",
    }

    for src in templates.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(templates)
        if rel.parts and rel.parts[0] == "field_logs":
            dest = evidence_dest / Path(*rel.parts[1:])
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_file() and not overwrite:
                continue
            shutil.copy2(src, dest)
            notes.append(f"synced evidence/{dest.name}")
            continue
        dest = records_dest / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and not overwrite:
            continue
        shutil.copy2(src, dest)
        notes.append(f"synced {rel}")

    start_dest = CLOUD_MIRROR_DIR / "00_START_HERE"
    for src in templates.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(templates)
        if rel.parts and rel.parts[0] in records_skip_in_start:
            continue
        if rel.parts and rel.parts[0] == "field_logs":
            continue
        dest = start_dest / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and not overwrite:
            continue
        shutil.copy2(src, dest)
        notes.append(f"synced 00_START_HERE/{rel}")

    return notes


def _bootstrap_mirror_from_templates(base_dir: Path) -> List[str]:
    """Seed cloud mirror from repo templates when live Dropbox is unavailable."""
    notes = _push_templates_to_mirror(base_dir, overwrite=False)
    (CLOUD_MIRROR_DIR / ".jrc_dropbox_mirror").write_text("template-bootstrap\n", encoding="utf-8")
    return notes


def _bootstrap_jackie_evidence_from_git(base_dir: Path) -> List[str]:
    """Copy 403 Jackie field logs from git branch into mirror evidence when present."""
    import subprocess

    notes: List[str] = []
    evidence_dest = CLOUD_MIRROR_DIR / "evidence"
    evidence_dest.mkdir(parents=True, exist_ok=True)
    branch = "origin/cursor/jackie-deck-rebuild-log-59da"
    files = [
        "evidence/Jackie_Deck_Rebuild_Field_Log_2026-06-29.txt",
        "evidence/Jackie_Deck_Rebuild_Finish_Log_2026-06-30.txt",
        "evidence/Jackie_Deck_Rebuild_Materials_Correction_2026-06-29.txt",
    ]
    for rel in files:
        dest = evidence_dest / Path(rel).name
        try:
            proc = subprocess.run(
                ["git", "show", f"{branch}:{rel}"],
                cwd=base_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            dest.write_text(proc.stdout, encoding="utf-8")
            notes.append(f"evidence {dest.name}")
        except (subprocess.CalledProcessError, OSError):
            pass
    return notes


def sync_dropbox_mirror(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Sync Dropbox office files into local mirror, then run office records sync.

    Priority:
    1. Local Dropbox sync (office PC) — use as-is
    2. Dropbox API — download office CSVs into mirror
    3. Template bootstrap — seed mirror from repo templates
    """
    base = base_dir or BASE_DIR
    report: Dict[str, Any] = {
        "mode": access_mode(),
        "synced_files": [],
        "notes": [],
        "errors": [],
        "office_sync": None,
    }

    local_records = resolve_dropbox_records(base)
    if local_records and str(local_records).startswith(str(CLOUD_MIRROR_DIR)) is False:
        report["mode"] = "local"
        report["dropbox_records"] = str(local_records)
        report["notes"].append("Using local Dropbox Desktop sync — no mirror download needed.")
        try:
            from app.office_records_sync import run_office_sync

            report["office_sync"] = run_office_sync(base)
        except Exception as exc:
            report["errors"].append(f"office sync failed: {exc}")
        return report

    CLOUD_MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    token = get_dropbox_access_token()
    api_root = get_api_root()

    if token:
        report["mode"] = "api"
        prefix = api_root.rstrip("/")
        for rel in OFFICE_SYNC_PATHS:
            dropbox_path = f"{prefix}/{rel}" if prefix else f"/{rel}"
            local = sync_file_from_api(dropbox_path)
            if local:
                report["synced_files"].append(str(local))
            else:
                report["notes"].append(f"API miss (will bootstrap if needed): {rel}")
        try:
            for hit in api_search("403 Jackie deck rebuild", limit=10):
                path = hit.get("path") or ""
                if path and hit.get("name", "").endswith((".txt", ".csv")):
                    local = sync_file_from_api(path)
                    if local:
                        report["synced_files"].append(str(local))
        except Exception as exc:
            report["notes"].append(f"API search skipped: {exc}")
    else:
        report["notes"].append(
            "No DROPBOX_ACCESS_TOKEN — using template bootstrap into dropbox-business mirror."
        )

    records_marker = CLOUD_MIRROR_DIR / "dropbox-records" / REGISTER_MARKER
    if not records_marker.is_file():
        report["notes"].extend(_bootstrap_mirror_from_templates(base))
    else:
        pushed = _push_templates_to_mirror(base, overwrite=True)
        report["notes"].append(f"pushed {len(pushed)} template file(s) to mirror")
        if len(pushed) <= 12:
            report["notes"].extend(pushed)
        else:
            report["notes"].extend(pushed[:8])
            report["notes"].append(f"... and {len(pushed) - 8} more")
    report["notes"].extend(_bootstrap_jackie_evidence_from_git(base))
    (CLOUD_MIRROR_DIR / ".jrc_dropbox_mirror").write_text(
        f"synced {datetime.now().isoformat(timespec='seconds')}\n",
        encoding="utf-8",
    )

    os.environ.setdefault("JRC_DROPBOX_RECORDS", str(CLOUD_MIRROR_DIR / "dropbox-records"))
    os.environ.setdefault("JRC_DROPBOX_MIRROR", str(CLOUD_MIRROR_DIR))

    resolved = resolve_dropbox_records(base)
    report["dropbox_records"] = str(resolved) if resolved else None
    if not resolved:
        report["errors"].append("Mirror sync finished but dropbox-records register still missing.")
        return report

    db_path = base / "data" / "jr_business.db"
    if not db_path.is_file():
        try:
            data_dir = base / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("JRC_DATA_DIR", str(data_dir))
            os.environ.setdefault("JRC_DB_PATH", str(db_path))
            import sys

            app_dir = str(base / "app")
            if app_dir not in sys.path:
                sys.path.insert(0, app_dir)
            from seed_current_records import seed

            seed()
            report["notes"].append(f"seeded database for office sync: {db_path}")
        except Exception as exc:
            report["notes"].append(f"database seed skipped: {exc}")

    try:
        from app.office_records_sync import run_office_sync

        report["office_sync"] = run_office_sync(base)
        report["notes"].append("office records sync completed")
    except Exception as exc:
        report["errors"].append(f"office sync failed: {exc}")

    upload_notes = push_mirror_to_live_dropbox()
    if upload_notes:
        report["dropbox_uploads"] = upload_notes
        report["notes"].extend(upload_notes[:15])
        if len(upload_notes) > 15:
            report["notes"].append(f"... and {len(upload_notes) - 15} more uploads")

    verify = verify_phone_session_files()
    report["phone_verify"] = verify
    if not verify.get("ok"):
        report["notes"].append("phone session verify: SOME CHECKS FAILED (see --verify-phone)")
        for c in verify.get("checks") or []:
            if not c.get("ok"):
                report["notes"].append(f"verify: {c.get('file')} — {c.get('error', 'marker missing')}")
    else:
        report["notes"].append("phone session verify: ALL CRITICAL FILES OK")

    return report


def format_sync_report(report: Dict[str, Any]) -> str:
    lines = [
        "J & R Construction — Dropbox Sync Report",
        f"Mode: {report.get('mode')}",
        f"dropbox-records: {report.get('dropbox_records') or 'NOT FOUND'}",
        "",
    ]
    files = report.get("synced_files") or []
    if files:
        lines.append(f"Downloaded {len(files)} file(s) via API:")
        lines.extend(f"  - {f}" for f in files[:20])
        lines.append("")
    notes = report.get("notes") or []
    if notes:
        lines.append("Notes:")
        lines.extend(f"  - {n}" for n in notes[:30])
    errors = report.get("errors") or []
    if errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {e}" for e in errors)
    office = report.get("office_sync")
    if isinstance(office, dict):
        lines.extend(
            [
                "",
                "Office sync:",
                f"  jobs inserted={office.get('jobs_inserted', 0)} updated={office.get('jobs_updated', 0)}",
                f"  payroll imported={office.get('payroll_rows_imported', 0)}",
                f"  owner draws imported={office.get('owner_draws_rows_imported', 0)}",
            ]
        )
    verify = report.get("phone_verify")
    if isinstance(verify, dict):
        lines.extend(
            [
                "",
                "Phone session verify:",
                f"  all critical files OK: {verify.get('ok')}",
            ]
        )
        if verify.get("missing"):
            lines.append(f"  missing: {', '.join(verify['missing'])}")
    return "\n".join(lines)


def format_check_report(report: Dict[str, Any]) -> str:
    lines = [
        "J & R Construction — Dropbox Business Workspace Check",
        f"Mode: {report.get('mode')}",
        f"Business root: {report.get('business_root') or 'NOT FOUND'}",
        f"dropbox-records: {report.get('dropbox_records') or 'NOT FOUND'}",
        f"Mirror dir: {report.get('mirror_dir')}",
        "",
        "Candidates:",
    ]
    for row in report.get("candidates_checked") or []:
        flag = "OK" if row.get("exists") else "missing"
        reg = " + register" if row.get("has_job_register") else ""
        lines.append(f"  [{flag}] {row.get('path')}{reg}")
    if report.get("api_account"):
        acct = report["api_account"]
        lines.extend(
            [
                "",
                "Dropbox API:",
                f"  Account: {acct.get('name')} <{acct.get('email')}>",
                f"  API root: {acct.get('root')}",
            ]
        )
    if report.get("errors"):
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {e}" for e in report["errors"])
    if report.get("notes"):
        lines.extend(["", "Notes:"])
        lines.extend(f"  - {n}" for n in report["notes"])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    base = Path(args[0]) if args and not args[0].startswith("-") else BASE_DIR
    if args and not args[0].startswith("-"):
        args = args[1:]

    if not args or args[0] in ("--check", "check"):
        report = check_access(base)
        print(format_check_report(report))
        return 1 if report.get("errors") else 0

    if args[0] in ("--search", "search"):
        query = " ".join(args[1:]).strip()
        if not query:
            print("Usage: python -m app.dropbox_workspace --search <query>")
            return 2
        if access_mode() == "none":
            report = check_access(base)
            print(format_check_report(report))
            return 1
        if access_mode() == "api":
            for hit in api_search(query):
                print(f"{hit.get('path')}\t{hit.get('name')}\t{hit.get('size')} bytes")
            return 0
        # local search
        root = resolve_business_root(base)
        if not root:
            print("No business root found.")
            return 1
        q = query.lower()
        for path in root.rglob("*"):
            if path.is_file() and q in path.name.lower():
                print(path)
        return 0

    if args[0] in ("--verify-phone", "verify-phone"):
        verify = verify_phone_session_files()
        print("Phone session file verify:")
        for c in verify.get("checks") or []:
            flag = "OK" if c.get("ok") else "FAIL"
            print(f"  [{flag}] {c.get('file')} — {c.get('error') or 'marker found'}")
        print(f"\nAll OK: {verify.get('ok')}")
        return 0 if verify.get("ok") else 1

    if args[0] in ("--sync", "sync", "--log", "log", "log-update-sync"):
        report = sync_dropbox_mirror(base)
        print(format_sync_report(report))
        return 1 if report.get("errors") else 0

    print("Usage: python -m app.dropbox_workspace [--check | --search <query> | --sync | --log]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
