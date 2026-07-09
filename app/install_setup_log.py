"""
Install / login / setup journal — one place for save, state, and logs.

Files written under the install folder:
  logs/install_setup_journal.log   — append-only human-readable log
  data/install_setup_state.json    — latest setup progress (machine-readable)
  INSTALL_SETUP_REPORT.txt         — plain-English summary for owner/customer
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

JOURNAL_NAME = "install_setup_journal.log"
STATE_NAME = "install_setup_state.json"
REPORT_NAME = "INSTALL_SETUP_REPORT.txt"
AUTH_NAME = "install_auth.json"
PROFILE_NAME = "install_profile.json"

STEPS = (
    "choose_profile",
    "verify_login",
    "install_files",
    "runtime_setup",
    "emergency_access",
    "post_login",
    "setup_complete",
)


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def paths(base_dir: Path) -> Dict[str, Path]:
    base = Path(base_dir).resolve()
    data = base / "data"
    logs = base / "logs"
    return {
        "base": base,
        "data": data,
        "logs": logs,
        "journal": logs / JOURNAL_NAME,
        "state": data / STATE_NAME,
        "report": base / REPORT_NAME,
        "auth": data / AUTH_NAME,
        "profile": data / PROFILE_NAME,
    }


def ensure_dirs(base_dir: Path) -> Dict[str, Path]:
    p = paths(base_dir)
    p["data"].mkdir(parents=True, exist_ok=True)
    p["logs"].mkdir(parents=True, exist_ok=True)
    return p


def load_state(base_dir: Path) -> Dict[str, Any]:
    p = ensure_dirs(base_dir)
    if not p["state"].exists():
        return {"created_at": _now(), "steps": {}, "events": []}
    try:
        return json.loads(p["state"].read_text(encoding="utf-8"))
    except Exception:
        return {"created_at": _now(), "steps": {}, "events": []}


def save_state(base_dir: Path, state: Dict[str, Any]) -> None:
    p = ensure_dirs(base_dir)
    state["updated_at"] = _now()
    p["state"].write_text(json.dumps(state, indent=2), encoding="utf-8")


def log_event(
    base_dir: Path,
    category: str,
    message: str,
    *,
    level: str = "INFO",
    step: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    p = ensure_dirs(base_dir)
    line = f"[{_now()}] [{level}] [{category}] {message}"
    with p["journal"].open("a", encoding="utf-8", errors="replace") as f:
        f.write(line + "\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    state = load_state(base_dir)
    event = {"time": _now(), "level": level, "category": category, "message": message}
    if step:
        event["step"] = step
        state.setdefault("steps", {})[step] = {"status": "ok" if level != "ERROR" else "error", "time": _now(), "message": message}
    if extra:
        event.update(extra)
    state.setdefault("events", []).append(event)
    if len(state["events"]) > 200:
        state["events"] = state["events"][-200:]
    save_state(base_dir, state)


def mark_step(base_dir: Path, step: str, status: str, message: str = "") -> None:
    state = load_state(base_dir)
    state.setdefault("steps", {})[step] = {"status": status, "time": _now(), "message": message}
    save_state(base_dir, state)
    log_event(base_dir, "SetupStep", message or f"{step}: {status}", level="INFO" if status != "error" else "ERROR", step=step)


def get_suggested_admin_username(base_dir: Path) -> str:
    from app.role_utils import DEFAULT_OWNER_USERNAME

    db_path = Path(base_dir) / "data" / "jr_business.db"
    if not db_path.exists():
        return DEFAULT_OWNER_USERNAME
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT username FROM users WHERE active=1 AND LOWER(role)='admin' ORDER BY id LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row["username"]:
            return str(row["username"])
    except Exception:
        pass
    return DEFAULT_OWNER_USERNAME


def users_exist(base_dir: Path) -> bool:
    db_path = Path(base_dir) / "data" / "jr_business.db"
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(db_path)
        n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        return int(n or 0) > 0
    except Exception:
        return False


def write_setup_report(base_dir: Path) -> Path:
    p = ensure_dirs(base_dir)
    state = load_state(base_dir)
    auth = {}
    profile = {}
    try:
        if p["auth"].exists():
            auth = json.loads(p["auth"].read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        if p["profile"].exists():
            profile = json.loads(p["profile"].read_text(encoding="utf-8"))
    except Exception:
        pass

    steps = state.get("steps", {})
    lines = [
        "J and R Construction Manager — Install / Setup Report",
        "=" * 62,
        f"Generated: {_now()}",
        f"Install folder: {p['base']}",
        "",
        "WHO IS THIS FOR?",
        "- Owner / Jacob PC: full business data, admin tools, Office app, web admin.",
        "- Worker PC: app shell only — connect to owner host or cloud URL.",
        "- Customer / outside user: NO installer needed. Owner shares browser link only.",
        "",
        "SETUP PROGRESS",
    ]
    labels = {
        "choose_profile": "1) Choose install profile",
        "verify_login": "2) Verify login or create owner",
        "install_files": "3) Install / update program files",
        "runtime_setup": "4) Python runtime setup",
        "emergency_access": "5) Owner emergency mastery key",
        "post_login": "6) Post-install login check",
        "setup_complete": "7) Setup complete",
    }
    for key, label in labels.items():
        info = steps.get(key, {})
        status = info.get("status", "pending")
        msg = info.get("message", "")
        lines.append(f"  [{status.upper():7}] {label}" + (f" — {msg}" if msg else ""))

    lines.extend(
        [
            "",
            "VERIFIED ACCESS",
            f"  Profile: {profile.get('profile', 'unknown')}",
            f"  Verified user: {auth.get('username') or profile.get('verified_user') or '(not recorded)'}",
            f"  Role: {auth.get('role') or profile.get('verified_role') or '(not recorded)'}",
            f"  Verified at: {auth.get('verified_at') or profile.get('verified_at') or '(not recorded)'}",
            "",
            "IMPORTANT SECURITY NOTES",
            "  • Passwords are NEVER written to installer logs.",
            "  • First-setup default (this PC only): ivygrows / ivygrows — change immediately.",
            "  • Owner emergency mastery key: data\\local_secrets.env (default ivygrows1 on Owner Master install).",
            "  • Emergency access: Local Login Gate → Emergency Owner, or web /emergency-access.",
            "  • Customers never install this program — share /register or /mobile links only.",
            "",
            "LOG FILES",
            f"  Journal: {p['journal']}",
            f"  State:   {p['state']}",
            "",
            "NEXT STEPS (OWNER PC)",
            "  1. Open Start Center from Desktop shortcut",
            "  2. Daily work → Open Office",
            "  3. Admin & security → Start Local Host → Admin Web Panel",
            "  4. Change owner password if still using first-setup default",
            "",
            "NEXT STEPS (CUSTOMERS / REMOTE USERS)",
            "  • Ask Jacob for the company web/cloud link",
            "  • Use Request Access (/register) — admin approves accounts",
            "  • Do NOT run this Windows installer on customer phones/PCs unless instructed",
            "",
        ]
    )
    recent = state.get("events", [])[-12:]
    if recent:
        lines.append("RECENT EVENTS")
        for ev in recent:
            lines.append(f"  [{ev.get('time','')}] {ev.get('category','')}: {ev.get('message','')}")
        lines.append("")

    p["report"].write_text("\n".join(lines), encoding="utf-8")
    log_event(base_dir, "Report", f"Wrote {REPORT_NAME}", extra={"report_path": str(p["report"])})
    return p["report"]


def record_program_update(
    base_dir: Path,
    title: str,
    changes: list[str],
    *,
    version: str = "",
    notes: Optional[list[str]] = None,
) -> Dict[str, Path]:
    """Log a program update, save export report, and refresh INSTALL_SETUP_REPORT.txt."""
    p = ensure_dirs(base_dir)
    ts = _now()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    try:
        from app.program_manifest import APP_VERSION

        version = version or APP_VERSION
    except Exception:
        version = version or "unknown"

    lines = [
        "J and R Construction Manager — PROGRAM UPDATE RECORD",
        "=" * 62,
        f"Generated: {ts}",
        f"Version: {version}",
        f"Install folder: {p['base']}",
        f"Title: {title}",
        "",
        "CHANGES",
    ]
    for item in changes:
        lines.append(f"  • {item}")
    if notes:
        lines.append("")
        lines.append("NOTES")
        for note in notes:
            lines.append(f"  • {note}")
    lines.extend(
        [
            "",
            "LOG FILES",
            f"  Journal: {p['journal']}",
            f"  State:   {p['state']}",
            f"  Report:  {p['report']}",
        ]
    )

    export_name = f"JRC_Program_Update_{stamp}.txt"
    export_path = p["base"] / "exports" / export_name
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text("\n".join(lines), encoding="utf-8")

    latest_path = p["base"] / "PROGRAM_UPDATE_REPORT.txt"
    latest_path.write_text("\n".join(lines), encoding="utf-8")

    summary = f"{title} ({version}) — saved {export_name}"
    log_event(
        base_dir,
        "ProgramUpdate",
        summary,
        level="INFO",
        step="setup_complete",
        extra={
            "version": version,
            "title": title,
            "export_report": str(export_path),
            "latest_report": str(latest_path),
            "changes": changes,
        },
    )
    write_setup_report(base_dir)
    return {"export": export_path, "latest": latest_path, "journal": p["journal"], "setup_report": p["report"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JRC install setup journal helper")
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--log", nargs=3, metavar=("CATEGORY", "LEVEL", "MESSAGE"))
    parser.add_argument("--step", nargs=2, metavar=("STEP", "STATUS"))
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args(argv)
    base = Path(args.install_dir)
    if args.log:
        log_event(base, args.log[0], args.log[2], level=args.log[1].upper())
    if args.step:
        mark_step(base, args.step[0], args.step[1])
    if args.write_report:
        write_setup_report(base)
        print(write_setup_report.__doc__)
        print(paths(base)["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
