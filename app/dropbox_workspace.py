# -*- coding: utf-8 -*-
"""Resolve J&R business workspace from local Dropbox sync or Dropbox API (cloud agents)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
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


_CACHED_ACCESS_TOKEN: Optional[str] = None


def get_dropbox_refresh_credentials() -> Tuple[str, str, str]:
    """Return (refresh_token, app_key, app_secret) when configured for long-lived access."""
    return (
        os.environ.get("DROPBOX_REFRESH_TOKEN", "").strip()
        or os.environ.get("JRC_DROPBOX_REFRESH_TOKEN", "").strip(),
        os.environ.get("DROPBOX_APP_KEY", "").strip()
        or os.environ.get("JRC_DROPBOX_APP_KEY", "").strip(),
        os.environ.get("DROPBOX_APP_SECRET", "").strip()
        or os.environ.get("JRC_DROPBOX_APP_SECRET", "").strip(),
    )


def refresh_dropbox_access_token(*, force: bool = False) -> str:
    """Exchange refresh token for a short-lived access token (Dropbox OAuth2)."""
    global _CACHED_ACCESS_TOKEN
    if _CACHED_ACCESS_TOKEN and not force:
        return _CACHED_ACCESS_TOKEN
    refresh, app_key, app_secret = get_dropbox_refresh_credentials()
    if not (refresh and app_key and app_secret):
        raise RuntimeError(
            "Dropbox refresh credentials missing. Set DROPBOX_REFRESH_TOKEN, "
            "DROPBOX_APP_KEY, and DROPBOX_APP_SECRET as Cursor Personal secrets."
        )
    url = "https://api.dropboxapi.com/oauth2/token"
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": app_key,
            "client_secret": app_secret,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dropbox token refresh failed ({exc.code}): {detail}") from exc
    token = (data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Dropbox token refresh returned no access_token.")
    _CACHED_ACCESS_TOKEN = token
    os.environ["DROPBOX_ACCESS_TOKEN"] = token
    return token


def get_dropbox_access_token() -> str:
    global _CACHED_ACCESS_TOKEN
    direct = (
        os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip()
        or os.environ.get("JRC_DROPBOX_ACCESS_TOKEN", "").strip()
    )
    if direct:
        _CACHED_ACCESS_TOKEN = direct
        return direct
    refresh, app_key, app_secret = get_dropbox_refresh_credentials()
    if refresh and app_key and app_secret:
        return refresh_dropbox_access_token()
    return ""


def has_dropbox_credentials() -> bool:
    direct = (
        os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip()
        or os.environ.get("JRC_DROPBOX_ACCESS_TOKEN", "").strip()
        or (_CACHED_ACCESS_TOKEN or "")
    )
    if direct:
        return True
    refresh, app_key, app_secret = get_dropbox_refresh_credentials()
    return bool(refresh and app_key and app_secret)


def get_api_root() -> str:
    """Dropbox API path prefix, e.g. /dropbox-records or empty for account root."""
    root = os.environ.get("DROPBOX_API_ROOT", "").strip()
    if root and not root.startswith("/"):
        root = "/" + root
    return root.rstrip("/")


def access_mode() -> str:
    if resolve_business_root():
        return "local"
    if has_dropbox_credentials():
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
        # One retry after refresh when short-lived token expired.
        if exc.code == 401 and get_dropbox_refresh_credentials()[0]:
            refresh_dropbox_access_token(force=True)
            headers["Authorization"] = f"Bearer {get_dropbox_access_token()}"
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
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
        if exc.code == 401 and get_dropbox_refresh_credentials()[0]:
            refresh_dropbox_access_token(force=True)
            headers["Authorization"] = f"Bearer {get_dropbox_access_token()}"
            req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        raise RuntimeError(f"Dropbox download failed ({exc.code}): {detail}") from exc


# Essential relative paths mirrored for mobile Cursor cloud agents.
ESSENTIAL_MIRROR_PATHS: Tuple[str, ...] = (
    "08_Admin_Standards/JRC_JOB_RELATION_REGISTER.csv",
    "08_Admin_Standards/2026-07-14__JRC-ADM__CURSOR_UNFINISHED_WORK_NOTE.txt",
    "08_Admin_Standards/CURRENT_TO_DO.txt",
    "08_Admin_Standards/BUSINESS_HOURS_STANDARD.txt",
    "08_Admin_Standards/WEEKLY_CALENDAR_AGENDA.txt",
    "00_START_HERE/PHONE_CURSOR_DROPBOX_WORKSPACE.txt",
    "00_START_HERE/IPHONE_CURSOR_BOOKMARK_SETUP.txt",
    "00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt",
    "00_START_HERE/READABLE/BUSINESS_DASHBOARD.txt",
    "00_START_HERE/IPHONE_PHOTO_RECEIPT_UPLOAD_GUIDE.txt",
    "00_START_HERE/2026-07-23_JRC-ADM_PHONE_OFFICE_SYNC_OWNERSHIP_LOCK.txt",
)


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
        if exc.code == 401 and get_dropbox_refresh_credentials()[0]:
            refresh_dropbox_access_token(force=True)
            headers["Authorization"] = f"Bearer {get_dropbox_access_token()}"
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
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


def api_list_folder(dropbox_path: str = "", *, recursive: bool = False) -> List[Dict[str, Any]]:
    """List files/folders under a Dropbox path (absolute API path or under API root)."""
    path = dropbox_path.strip()
    if path and not path.startswith("/"):
        path = _dropbox_api_path(path)
    payload: Dict[str, Any] = {
        "path": path or get_api_root() or "",
        "recursive": recursive,
        "include_non_downloadable_files": False,
    }
    data = _api_json("files/list_folder", payload)
    entries: List[Dict[str, Any]] = list(data.get("entries") or [])
    cursor = data.get("cursor")
    while data.get("has_more") and cursor:
        data = _api_json("files/list_folder/continue", {"cursor": cursor})
        entries.extend(data.get("entries") or [])
        cursor = data.get("cursor")
    return entries


def bootstrap_essential_mirror(
    *,
    extra_paths: Optional[List[str]] = None,
    include_templates: bool = True,
) -> Dict[str, Any]:
    """Download essential business files into dropbox-business for mobile cloud agents."""
    report: Dict[str, Any] = {
        "ok": False,
        "mirrored": [],
        "missing": [],
        "errors": [],
        "mirror_dir": str(CLOUD_MIRROR_DIR),
    }
    if not has_dropbox_credentials():
        report["errors"].append(
            "No Dropbox credentials. Add DROPBOX_ACCESS_TOKEN (or refresh trio) as Cursor Personal secrets."
        )
        return report

    CLOUD_MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    if include_templates:
        templates = BASE_DIR / "scripts" / "templates" / "dropbox_workspace"
        if templates.is_dir():
            import shutil

            dest = CLOUD_MIRROR_DIR / "00_START_HERE"
            dest.mkdir(parents=True, exist_ok=True)
            for src in templates.rglob("*"):
                if not src.is_file():
                    continue
                target = dest / src.relative_to(templates)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                report["mirrored"].append(f"template:{src.relative_to(templates).as_posix()}")

    paths = list(ESSENTIAL_MIRROR_PATHS)
    if extra_paths:
        paths.extend(extra_paths)

    for rel in paths:
        api_path = _dropbox_api_path(rel)
        try:
            local = mirror_file(api_path)
            report["mirrored"].append(str(local))
        except Exception as exc:
            msg = str(exc)
            if "path/not_found" in msg or "not_found" in msg.lower():
                report["missing"].append(rel)
            else:
                report["errors"].append(f"{rel}: {exc}")

    # Prefer live register as the readiness signal.
    if _has_register(CLOUD_MIRROR_DIR):
        report["ok"] = True
    elif report["mirrored"] and not report["errors"]:
        report["ok"] = True
        report["errors"].append(
            "Mirrored some files but job register not found — check DROPBOX_API_ROOT points at dropbox-records."
        )
        report["ok"] = False
    (CLOUD_MIRROR_DIR / ".jrc_dropbox_mirror").write_text("api\n", encoding="utf-8")
    return report


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
        "credentials": {
            "access_token": bool(
                os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip()
                or os.environ.get("JRC_DROPBOX_ACCESS_TOKEN", "").strip()
            ),
            "refresh_configured": bool(all(get_dropbox_refresh_credentials())),
        },
        "errors": [],
        "notes": [
            "GitHub stores application source only — business files live in Dropbox.",
            "Mobile cloud agents: set DROPBOX secrets in Cursor → Cloud Agents → Secrets (Personal scope).",
            "Preferred long-lived setup: DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET.",
            "Also set DROPBOX_API_ROOT=/dropbox-records (Environment Variable, not secret).",
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
    if has_dropbox_credentials():
        try:
            acct = api_account_check()
            report["api_account"] = {
                "name": acct.get("name", {}).get("display_name"),
                "email": acct.get("email"),
                "root": get_api_root() or "/",
            }
            if report["mode"] == "api":
                report["notes"].append(
                    "Using Dropbox API — run: python3 -m app.mobile_cloud_access --bootstrap"
                )
        except Exception as exc:
            report["errors"].append(f"Dropbox API token invalid or unreachable: {exc}")
    elif report["mode"] == "none":
        report["errors"].append(
            "No local Dropbox sync and no Dropbox credentials. "
            "Add DROPBOX_ACCESS_TOKEN (or refresh trio) as Cursor Personal secrets, then start a new agent."
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

    if args[0] in ("--bootstrap", "bootstrap"):
        rep = bootstrap_essential_mirror()
        print(json.dumps(rep, indent=2))
        return 0 if rep.get("ok") else 1

    if args[0] in ("--upload", "upload"):
        if len(args) < 3:
            print("Usage: python -m app.dropbox_workspace --upload <local_path> <dropbox_relative_path>")
            return 2
        if not has_dropbox_credentials():
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
        if not has_dropbox_credentials():
            report = check_access(base)
            print(format_check_report(report))
            return 1
        local_dir = Path(args[1]).expanduser()
        results = api_upload_folder(local_dir, args[2])
        for row in results:
            print(f"{row['local']} -> {row['dropbox']} ({row.get('size')} bytes)")
        print(f"Uploaded {len(results)} file(s).")
        return 0

    print(
        "Usage: python -m app.dropbox_workspace "
        "[--check | --search <query> | --bootstrap | "
        "--upload <local> <dropbox_rel> | --upload-folder <local_dir> <dropbox_rel_dir>]"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
