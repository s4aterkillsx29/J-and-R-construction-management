"""Create or update dedicated host laptop user accounts (hostadmin, jrc_host)."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

from app.host_laptop_roles import data_dir, ensure_host_admin_user


def ensure_user_account(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    *,
    display_name: str = "",
    role: str = "admin",
    title: str = "",
    notes: str = "",
    must_change_password: int = 0,
) -> Tuple[bool, str]:
    from app.network_server import hash_password, now_iso

    username = (username or "").strip().lower()
    if not username or not password:
        return False, "Username and password required."

    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    salt, ph = hash_password(password)
    if row:
        conn.execute(
            "UPDATE users SET salt=?, password_hash=?, role=?, active=1, must_change_password=?, "
            "display_name=COALESCE(NULLIF(?, ''), display_name), title=COALESCE(NULLIF(?, ''), title), "
            "notes=COALESCE(NULLIF(?, ''), notes) WHERE username=?",
            (salt, ph, role, must_change_password, display_name, title, notes, username),
        )
        return True, f"Updated user {username}."

    conn.execute(
        "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, "
        "created_at, notes, title, owner_account) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 0)",
        (
            username,
            display_name or username,
            role,
            salt,
            ph,
            must_change_password,
            now_iso(),
            notes or f"Dedicated host account {username}.",
            title or "Host Administrator",
        ),
    )
    return True, f"Created user {username}."


def setup_host_accounts(
    install_dir: Path,
    hostadmin_password: str,
    *,
    also_jrc_host: bool = True,
) -> list[str]:
    from app.network_server import init_db

    root = install_dir.resolve()
    db_path = data_dir(root) / "jr_business.db"
    if not db_path.exists():
        return [f"No database at {db_path} — run dedicated setup first."]

    init_db()
    results: list[str] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ok, msg = ensure_user_account(
            conn,
            "hostadmin",
            hostadmin_password,
            display_name="Host Administrator",
            role="admin",
            title="Dedicated Host Admin",
            notes="Primary local host operator login for DESKTOP-J3KPDS1 / JRCManagerHost.",
            must_change_password=0,
        )
        results.append(msg)
        if also_jrc_host:
            ok2, msg2 = ensure_host_admin_user(conn, None)
            results.append(msg2)
        conn.commit()
    return results


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create hostadmin on dedicated host laptop")
    parser.add_argument("--install-dir", default=".")
    parser.add_argument("--hostadmin-password", required=True)
    parser.add_argument("--skip-jrc-host", action="store_true")
    args = parser.parse_args(argv)
    lines = setup_host_accounts(
        Path(args.install_dir),
        args.hostadmin_password,
        also_jrc_host=not args.skip_jrc_host,
    )
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
