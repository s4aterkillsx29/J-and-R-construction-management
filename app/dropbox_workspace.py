# -*- coding: utf-8 -*-
"""Resolve J&R business workspace from local Dropbox sync or Dropbox API (cloud agents)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
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


def _dropbox_api_path(relative_path: str) -> str:
    """Build a Dropbox API path from a relative path under DROPBOX_API_ROOT."""
    rel = relative_path.replace("\\", "/").lstrip("/")
    root = get_api_root()
    if not root:
        return f"/{rel}" if rel else "/"
    return f"{root}/{rel}" if rel else root


def api_upload(local_path: Path, dropbox_relative_path: str, *, overwrite: bool = True) -> Dict[str, Any]:
    """Upload one local file to Dropbox (requires files.content.write scope)."""
    token = get_dropbox_access_token()
    if not token:
        raise RuntimeError("DROPBOX_ACCESS_TOKEN is not set.")
    if not local_path.is_file():
        raise FileNotFoundError(f"Local file not found: {local_path}")
    dropbox_path = _dropbox_api_path(dropbox_relative_path)
    url = "https://content.dropboxapi.com/2/files/upload"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "Dropbox-API-Arg": json.dumps(
            {"path": dropbox_path, "mode": "overwrite" if overwrite else "add", "autorename": not overwrite}
        ),
    }
    data = local_path.read_bytes()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dropbox upload failed ({exc.code}): {detail}") from exc


def api_upload_folder(
    local_dir: Path,
    dropbox_relative_dir: str,
    *,
    overwrite: bool = True,
) -> List[Dict[str, Any]]:
    """Upload all files under local_dir to Dropbox, preserving relative paths."""
    if not local_dir.is_dir():
        raise NotADirectoryError(f"Local folder not found: {local_dir}")
    results: List[Dict[str, Any]] = []
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local_dir).as_posix()
        target = f"{dropbox_relative_dir.rstrip('/')}/{rel}" if dropbox_relative_dir else rel
        meta = api_upload(path, target, overwrite=overwrite)
        results.append({"local": str(path), "dropbox": meta.get("path_display", target), "size": meta.get("size")})
    return results


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

    if args[0] in ("--upload", "upload"):
        if len(args) < 3:
            print("Usage: python -m app.dropbox_workspace --upload <local_path> <dropbox_relative_path>")
            return 2
        if not get_dropbox_access_token():
            report = check_access(base)
            print(format_check_report(report))
            return 1
        local_path = Path(args[1]).expanduser()
        meta = api_upload(local_path, args[2])
        print(f"Uploaded {local_path} -> {meta.get('path_display')}")
        return 0

    if args[0] in ("--upload-folder", "upload-folder"):
        if len(args) < 3:
            print("Usage: python -m app.dropbox_workspace --upload-folder <local_dir> <dropbox_relative_dir>")
            return 2
        if not get_dropbox_access_token():
            report = check_access(base)
            print(format_check_report(report))
            return 1
        local_dir = Path(args[1]).expanduser()
        results = api_upload_folder(local_dir, args[2])
        for row in results:
            print(f"{row['local']} -> {row['dropbox']} ({row.get('size')} bytes)")
        print(f"Uploaded {len(results)} file(s).")
        return 0

    print("Usage: python -m app.dropbox_workspace [--check | --search <query> | --upload <local> <dropbox_rel> | --upload-folder <local_dir> <dropbox_rel_dir>]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
