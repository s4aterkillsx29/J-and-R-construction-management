# -*- coding: utf-8 -*-
"""Ensure Jacob has one active owner admin (admin) — deactivate extras until host PC account is added."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

OWNER_USERNAME = "admin"
OWNER_DISPLAY = "Jacob Cosentino"
OWNER_EMAIL = "enragementwow@hotmail.com"
OWNER_PHONE = "(910) 712-0936"


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 250000).hex()
    return salt, digest


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def default_db_paths() -> list[Path]:
    home = Path.home()
    return [
        Path(__import__("os").environ.get("LOCALAPPDATA", "")) / "J_and_R_Construction_Manager" / "data" / "jr_business.db",
        home / "OneDrive" / "Desktop" / "J and R Construction Manager" / "data" / "jr_business.db",
        home / "Documents" / "JRC" / "J-and-R-construction-management" / "data" / "jr_business.db",
    ]


def consolidate_db(db_path: Path, password: str, *, dry_run: bool = False) -> dict:
    if not db_path.exists():
        return {"path": str(db_path), "status": "missing", "changes": []}
    changes: list[str] = []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, username, role, active, owner_account FROM users ORDER BY id").fetchall()
        admins = [r for r in rows if (r["role"] or "").lower() == "admin" and r["active"]]
        if len(admins) > 1:
            changes.append(f"Found {len(admins)} active admin accounts — consolidating to {OWNER_USERNAME} only")

        admin_row = conn.execute("SELECT id FROM users WHERE username=?", (OWNER_USERNAME,)).fetchone()
        salt, ph = hash_password(password)

        if dry_run:
            for r in rows:
                if r["username"] == OWNER_USERNAME:
                    changes.append(f"Would set owner admin active: {r['username']}")
                elif r["active"]:
                    changes.append(f"Would deactivate: {r['username']} ({r['role']})")
            return {"path": str(db_path), "status": "dry_run", "changes": changes}

        if admin_row:
            conn.execute(
                """UPDATE users SET display_name=?, role='admin', salt=?, password_hash=?, active=1,
                   must_change_password=0, owner_account=1, email=?, recovery_email=?, phone=?, title=?,
                   notes=? WHERE username=?""",
                (
                    OWNER_DISPLAY,
                    salt,
                    ph,
                    OWNER_EMAIL,
                    OWNER_EMAIL,
                    OWNER_PHONE,
                    "Owner / Administrator",
                    f"Single owner admin consolidated {now_iso()}. Dedicated host owner account deferred.",
                    OWNER_USERNAME,
                ),
            )
            changes.append(f"Updated owner admin: {OWNER_USERNAME}")
        else:
            conn.execute(
                """INSERT INTO users (username, display_name, role, salt, password_hash, active,
                   must_change_password, created_at, notes, email, recovery_email, phone, title, owner_account)
                   VALUES (?,?,?,?,?,1,0,?,?,?,?,?,?,1)""",
                (
                    OWNER_USERNAME,
                    OWNER_DISPLAY,
                    "admin",
                    salt,
                    ph,
                    now_iso(),
                    f"Owner admin created {now_iso()}.",
                    OWNER_EMAIL,
                    OWNER_EMAIL,
                    OWNER_PHONE,
                    "Owner / Administrator",
                ),
            )
            changes.append(f"Created owner admin: {OWNER_USERNAME}")

        cur = conn.execute(
            "UPDATE users SET active=0, notes=COALESCE(notes,'') || ? WHERE username != ?",
            (f" | Deactivated {now_iso()} — single owner admin policy.", OWNER_USERNAME),
        )
        if cur.rowcount:
            changes.append(f"Deactivated {cur.rowcount} non-owner account(s)")

        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            ("admin_default_password_changed", "1"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            ("owner_setup_complete", "1"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            ("single_owner_admin_policy", now_iso()),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            ("dedicated_host_owner_deferred", "jrc_host account to be created on 24/7 host PC later"),
        )

        try:
            conn.execute(
                """INSERT INTO business_log (log_time, category, message, user_id, username, session_id)
                   VALUES (?, ?, ?, NULL, 'system', NULL)""",
                (
                    now_iso(),
                    "Admin",
                    f"Single owner admin policy applied — only {OWNER_USERNAME} active. Other accounts deactivated pending dedicated host setup.",
                ),
            )
        except Exception:
            pass

        conn.commit()

        active = conn.execute("SELECT username, role FROM users WHERE active=1").fetchall()
        changes.append(f"Active users now: {', '.join(r['username'] for r in active) or '(none)'}")
        return {"path": str(db_path), "status": "ok", "changes": changes}
    finally:
        conn.close()


def deactivate_non_owner_accounts(db_path: Path) -> dict:
    """Deactivate every account except owner admin — no password change."""
    if not db_path.exists():
        return {"path": str(db_path), "status": "missing", "changes": []}
    changes: list[str] = []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        admins = conn.execute(
            "SELECT username FROM users WHERE lower(role)='admin' AND active=1"
        ).fetchall()
        if len(admins) > 1:
            changes.append(f"Found {len(admins)} active admin accounts — deactivating non-owner")
        cur = conn.execute(
            "UPDATE users SET active=0 WHERE username != ?",
            (OWNER_USERNAME,),
        )
        if cur.rowcount:
            changes.append(f"Deactivated {cur.rowcount} non-owner account(s)")
        conn.execute(
            "UPDATE users SET active=1 WHERE username=?",
            (OWNER_USERNAME,),
        )
        conn.commit()
        active = conn.execute("SELECT username FROM users WHERE active=1").fetchall()
        changes.append(f"Active users now: {', '.join(r['username'] for r in active) or '(none)'}")
        return {"path": str(db_path), "status": "ok", "changes": changes}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate JRC to single owner admin account.")
    parser.add_argument("--password", help="Owner admin password (required unless --deactivate-only)")
    parser.add_argument("--deactivate-only", action="store_true", help="Deactivate non-owner accounts only; do not change admin password")
    parser.add_argument("--db", action="append", help="Database path (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = [Path(p) for p in args.db] if args.db else default_db_paths()
    paths = [p for p in paths if p]

    print("JRC Single Owner Admin Consolidation")
    print("=" * 50)
    errors = 0
    for p in paths:
        if args.deactivate_only:
            result = deactivate_non_owner_accounts(p)
        else:
            if not args.password:
                parser.error("--password is required unless --deactivate-only is set")
            result = consolidate_db(p, args.password, dry_run=args.dry_run)
        print(f"\n{result['path']} [{result['status']}]")
        for line in result.get("changes", []):
            print(f"  - {line}")
        if result["status"] == "missing":
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
