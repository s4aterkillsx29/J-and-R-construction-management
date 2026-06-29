# -*- coding: utf-8 -*-
"""Dropbox API + workspace check — paths resolved via app.jrc_workspace (one folder)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.jrc_workspace import (
    READABLE,
    START_HERE,
    WORKSPACE_MARKER,
    WORKSPACE_NAME,
    apply_workspace_env,
    resolve_business_root,
    resolve_dropbox_records,
    resolve_workspace,
    workspace_candidates,
    write_workspace_manifest,
)

BASE_DIR = Path(__file__).resolve().parents[1]

CLOUD_MIRROR_DIR = Path(
    os.environ.get("JRC_DROPBOX_MIRROR", str(BASE_DIR / "dropbox-business"))
).expanduser()

# Re-export unified workspace API (one folder for everything).
__all__ = [
    "WORKSPACE_NAME",
    "WORKSPACE_MARKER",
    "resolve_workspace",
    "resolve_dropbox_records",
    "resolve_business_root",
    "workspace_candidates",
    "check_access",
    "access_mode",
    "api_search",
    "api_download",
    "mirror_file",
]


def get_dropbox_access_token() -> str:
    return (
        os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip()
        or os.environ.get("JRC_DROPBOX_ACCESS_TOKEN", "").strip()
    )


def get_api_root() -> str:
    root = os.environ.get("DROPBOX_API_ROOT", "").strip()
    if not root:
        root = f"/{WORKSPACE_NAME}"
    if root and not root.startswith("/"):
        root = "/" + root
    return root.rstrip("/")


def access_mode() -> str:
    if resolve_workspace():
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
    options: Dict[str, Any] = {
        "path": get_api_root(),
        "max_results": min(max(limit, 1), 100),
        "file_status": "active",
    }
    data = _api_json("files/search_v2", {"query": query, "options": options})
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
    token = get_dropbox_access_token()
    if not token:
        raise RuntimeError("DROPBOX_ACCESS_TOKEN is not set.")
    url = "https://content.dropboxapi.com/2/files/download"
    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps({"path": dropbox_path}),
    }
    req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dropbox download failed ({exc.code}): {detail}") from exc


def mirror_file(dropbox_path: str, local_path: Optional[Path] = None) -> Path:
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
    from app.jrc_workspace import REGISTER_REL, ensure_unified_workspace

    base = base_dir or BASE_DIR
    unified = ensure_unified_workspace(base)
    root = unified.get("workspace")
    report: Dict[str, Any] = {
        "mode": access_mode(),
        "workspace": root,
        "workspace_name": WORKSPACE_NAME,
        "mirror_dir": str(CLOUD_MIRROR_DIR),
        "candidates_checked": [],
        "api_account": None,
        "errors": list(unified.get("errors") or []),
        "notes": [
            "One workspace: phone Cursor, office CSVs, quotes, and Manager share the same Dropbox folder.",
            "GitHub = app code only. Dropbox = all business files.",
        ],
    }
    if unified.get("notes"):
        report["notes"].extend(unified["notes"])
    for path in workspace_candidates(base):
        exists = path.is_dir()
        has_marker = (path / WORKSPACE_MARKER).is_file() if exists else False
        has_reg = (path / REGISTER_REL).is_file() if exists else False
        report["candidates_checked"].append(
            {
                "path": str(path),
                "exists": exists,
                "workspace_marker": has_marker,
                "has_job_register": has_reg,
            }
        )
    token = get_dropbox_access_token()
    if token:
        try:
            acct = api_account_check()
            report["api_account"] = {
                "name": acct.get("name", {}).get("display_name"),
                "email": acct.get("email"),
                "root": get_api_root(),
            }
        except Exception as exc:
            report["errors"].append(f"Dropbox API: {exc}")
    elif report["mode"] == "none":
        report["errors"].append(
            "No workspace on this PC. Sync Dropbox or set JRC_WORKSPACE_ROOT."
        )
    return report


def format_check_report(report: Dict[str, Any]) -> str:
    lines = [
        "J & R Construction — Unified Workspace Check",
        f"Mode: {report.get('mode')}",
        f"Workspace ({WORKSPACE_NAME}): {report.get('workspace') or 'NOT FOUND'}",
        f"Mirror: {report.get('mirror_dir')}",
        "",
        "Candidates:",
    ]
    for row in report.get("candidates_checked") or []:
        flags = []
        if row.get("workspace_marker"):
            flags.append("workspace")
        if row.get("has_job_register"):
            flags.append("register")
        extra = f" ({', '.join(flags)})" if flags else ""
        flag = "OK" if row.get("exists") else "missing"
        lines.append(f"  [{flag}] {row.get('path')}{extra}")
    if report.get("api_account"):
        acct = report["api_account"]
        lines.extend(
            [
                "",
                "Dropbox API:",
                f"  {acct.get('name')} <{acct.get('email')}>",
                f"  root: {acct.get('root')}",
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
            print(format_check_report(check_access(base)))
            return 1
        if access_mode() == "api":
            for hit in api_search(query):
                print(f"{hit.get('path')}\t{hit.get('name')}")
            return 0
        root = resolve_workspace(base)
        if not root:
            return 1
        q = query.lower()
        for path in root.rglob("*"):
            if path.is_file() and q in path.name.lower():
                print(path)
        return 0

    print("Usage: python -m app.dropbox_workspace [--check | --search <query>]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
