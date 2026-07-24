# -*- coding: utf-8 -*-
"""J&R mobile Cursor cloud access point — status, bootstrap, and verify Dropbox."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]

SECRET_SETUP_STEPS = """
ONE-TIME SETUP (Jacob — phone or office PC in DuckDuckGo / Cursor settings)
================================================================================
1. Open https://www.dropbox.com/developers/apps  (DuckDuckGo Desktop on PC)
2. Create app (Scoped access, Full Dropbox) OR open your existing JRC app.
3. Permissions: files.metadata.read, files.content.read, files.content.write
4. Preferred (does not expire every few hours):
     - Enable refresh tokens / offline access
     - Save App key, App secret, and a refresh token
5. In Cursor → Cloud Agents → Secrets → choose PERSONAL scope (not Environment):
     DROPBOX_REFRESH_TOKEN = <refresh token>
     DROPBOX_APP_KEY       = <app key>
     DROPBOX_APP_SECRET    = <app secret>
   OR short-lived fallback:
     DROPBOX_ACCESS_TOKEN  = <generated access token>
6. Add Environment Variable (not secret):
     DROPBOX_API_ROOT=/All Files/JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22/JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22
   (Older docs said /dropbox-records — that path does not exist on Jacob's Dropbox.)
7. Start a NEW mobile Cursor agent after saving secrets.
8. Ask it: "bootstrap mobile dropbox" or run:
     python3 -m app.mobile_cloud_access --bootstrap

VERIFY SUCCESS
  - Job register present under dropbox-business/08_Admin_Standards/
  - Unfinished work note readable
  - python3 -m app.mobile_cloud_access --status   → READY
""".strip()


def status_report() -> Dict[str, Any]:
    from app.dropbox_workspace import (
        CLOUD_MIRROR_DIR,
        check_access,
        resolve_business_root,
        resolve_dropbox_records,
    )

    access = check_access(BASE_DIR)
    root = resolve_business_root(BASE_DIR)
    records = resolve_dropbox_records(BASE_DIR)
    register = None
    unfinished = None
    if records:
        register = records / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
        unfinished_candidates = sorted(
            (records / "08_Admin_Standards").glob("*UNFINISHED_WORK_NOTE*.txt")
        ) if (records / "08_Admin_Standards").is_dir() else []
        unfinished = unfinished_candidates[-1] if unfinished_candidates else None
        todo = records / "08_Admin_Standards" / "CURRENT_TO_DO.txt"
    else:
        todo = None

    ready = bool(
        access.get("mode") in ("local", "api")
        and not access.get("errors")
        and (root or records)
        and register
        and register.is_file()
    )
    # API mode without bootstrap yet is "credentials OK, mirror pending"
    if access.get("mode") == "api" and access.get("api_account") and not (register and register.is_file()):
        ready = False

    return {
        "ready": ready,
        "role": "J&R mobile Cursor access point",
        "access": access,
        "business_root": str(root) if root else None,
        "dropbox_records": str(records) if records else None,
        "job_register": str(register) if register and register.is_file() else None,
        "unfinished_note": str(unfinished) if unfinished and unfinished.is_file() else None,
        "current_todo": str(todo) if todo and todo.is_file() else None,
        "mirror_dir": str(CLOUD_MIRROR_DIR),
        "next_steps": [] if ready else _next_steps(access, register),
    }


def _next_steps(access: Dict[str, Any], register: Optional[Path]) -> List[str]:
    steps: List[str] = []
    if access.get("mode") == "none":
        steps.append("Add Dropbox secrets (Personal scope) — see docs/guides/MOBILE_CLOUD_CURSOR_ACCESS.txt")
        steps.append("Start a NEW cloud agent after saving secrets")
        return steps
    if access.get("errors"):
        steps.extend(str(e) for e in access["errors"])
    if access.get("mode") == "api" and not (register and register.is_file()):
        steps.append("Run: python3 -m app.mobile_cloud_access --bootstrap")
    return steps


def apply_access_token(token: str) -> Dict[str, Any]:
    """Apply a Dropbox access token for this session, verify API, then bootstrap."""
    from app import dropbox_workspace as dw

    cleaned = (token or "").strip().strip('"').strip("'")
    if not cleaned or len(cleaned) < 20:
        return {"ok": False, "error": "Token missing or too short."}
    os.environ["DROPBOX_ACCESS_TOKEN"] = cleaned
    dw._CACHED_ACCESS_TOKEN = cleaned  # noqa: SLF001 — session cache for this process
    try:
        acct = dw.api_account_check()
    except Exception as exc:  # noqa: BLE001 — surface API errors to operator
        return {"ok": False, "error": f"Dropbox API rejected token: {exc}"}
    # Normalize account fields for status printing
    account = {
        "name": (acct.get("name") or {}).get("display_name") or acct.get("email"),
        "email": acct.get("email"),
        "root": (acct.get("root_info") or {}).get(".tag"),
        "raw": {k: acct.get(k) for k in ("account_id", "email", "country") if k in acct},
    }
    boot = bootstrap()
    return {
        "ok": True,
        "account": account,
        "bootstrap": boot.get("bootstrap"),
        "status": boot.get("status"),
    }


def bootstrap() -> Dict[str, Any]:
    from app.dropbox_workspace import bootstrap_essential_mirror

    mirrored = bootstrap_essential_mirror()
    status = status_report()
    return {"bootstrap": mirrored, "status": status}


def format_status(report: Dict[str, Any]) -> str:
    lines = [
        "J & R Construction — Mobile Cursor Access Point",
        f"Status: {'READY' if report.get('ready') else 'NOT READY'}",
        f"Mode: {(report.get('access') or {}).get('mode')}",
        f"Business root: {report.get('business_root') or 'NOT FOUND'}",
        f"dropbox-records: {report.get('dropbox_records') or 'NOT FOUND'}",
        f"Job register: {report.get('job_register') or 'MISSING'}",
        f"Unfinished note: {report.get('unfinished_note') or 'MISSING'}",
        f"CURRENT_TO_DO: {report.get('current_todo') or 'MISSING'}",
        f"Mirror: {report.get('mirror_dir')}",
    ]
    acct = (report.get("access") or {}).get("api_account")
    if acct:
        lines.append(f"Dropbox API: {acct.get('name')} <{acct.get('email')}> root={acct.get('root')}")
    cred = (report.get("access") or {}).get("credentials") or {}
    lines.append(
        f"Credentials: access_token={cred.get('access_token')} refresh={cred.get('refresh_configured')}"
    )
    if report.get("next_steps"):
        lines.append("")
        lines.append("Next steps:")
        lines.extend(f"  - {s}" for s in report["next_steps"])
    if not report.get("ready") and (report.get("access") or {}).get("mode") == "none":
        lines.extend(["", SECRET_SETUP_STEPS])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else "--status"

    if cmd in ("--help", "help", "-h"):
        print(
            "Usage: python3 -m app.mobile_cloud_access "
            "[--status | --bootstrap | --setup-help | --apply-token TOKEN | --json]"
        )
        return 0

    if cmd in ("--setup-help", "setup-help"):
        print(SECRET_SETUP_STEPS)
        return 0

    as_json = "--json" in args or cmd == "--json"

    if cmd in ("--apply-token", "apply-token"):
        token = ""
        if len(args) >= 2 and not args[1].startswith("--"):
            token = args[1]
        elif not sys.stdin.isatty():
            token = sys.stdin.read()
        result = apply_access_token(token)
        if as_json or "--json" in args:
            # Never echo the token back
            safe = {k: v for k, v in result.items() if k != "token"}
            if safe.get("status"):
                cred = ((safe["status"].get("access") or {}).get("credentials") or {})
                safe["credentials_present"] = bool(cred.get("access_token") or cred.get("refresh_configured"))
            print(json.dumps(safe, indent=2, default=str))
        else:
            if not result.get("ok"):
                print(f"Apply token failed: {result.get('error')}")
                return 1
            acct = result.get("account") or {}
            print(
                f"Dropbox connected: {acct.get('name')} <{acct.get('email')}> "
                f"root={acct.get('root')}"
            )
            boot = result.get("bootstrap") or {}
            print(f"Bootstrap ok={boot.get('ok')} mirrored={len(boot.get('mirrored') or [])}")
            print()
            print(format_status(result["status"]))
        return 0 if result.get("ok") and (result.get("status") or {}).get("ready") else (0 if result.get("ok") else 1)

    if cmd in ("--bootstrap", "bootstrap"):
        result = bootstrap()
        if as_json or "--json" in args:
            print(json.dumps(result, indent=2))
        else:
            boot = result["bootstrap"]
            print(f"Bootstrap ok={boot.get('ok')} mirrored={len(boot.get('mirrored') or [])}")
            if boot.get("missing"):
                print("Missing on Dropbox:", ", ".join(boot["missing"]))
            if boot.get("errors"):
                print("Errors:")
                for e in boot["errors"]:
                    print(f"  - {e}")
            print()
            print(format_status(result["status"]))
        return 0 if result["status"].get("ready") or result["bootstrap"].get("ok") else 1

    report = status_report()
    if as_json or cmd == "--json":
        print(json.dumps(report, indent=2))
    else:
        print(format_status(report))
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
