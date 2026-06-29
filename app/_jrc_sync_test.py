"""One-shot sync verification — run after live sync."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LIVE = Path(os.environ.get("JRC_LIVE_DIR") or os.path.expandvars(r"%LOCALAPPDATA%\J_and_R_Construction_Manager"))

errors: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        errors.append(f"{name}: {detail}")


def main() -> int:
    sys.path.insert(0, str(LIVE if LIVE.exists() else BASE))
    os.chdir(str(LIVE if LIVE.exists() else BASE))
    if LIVE.exists():
        os.environ.setdefault("JRC_DATA_DIR", str(LIVE / "data"))

    from app.role_utils import is_admin_role, migrate_user_roles, normalize_role

    check("normalize Admin->admin", normalize_role("Admin") == "admin")
    check("normalize User->viewer", normalize_role("User") == "viewer")
    check("is_admin_role Admin", is_admin_role("Admin"))

    db_path = Path(os.environ.get("JRC_DATA_DIR", str(BASE / "data"))) / "jr_business.db"
    if db_path.exists():
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        migrate_user_roles(conn)
        for row in conn.execute("SELECT username, role FROM users"):
            check(
                f"user {row['username']} role normalized",
                normalize_role(row["role"]) == row["role"],
                row["role"],
            )
        conn.close()
    else:
        print("[SKIP] no jr_business.db")

    from app import network_server as ns

    ns.init_db()
    with ns.app.app_context():
        for role in ("Admin", "admin", "Manager", "User"):
            check(
                f"view_admin for {role}",
                ns.has_permission_role(role, "view_admin") == (ns.normalize_role_for_session(role) == "admin"),
            )
        conn = ns.direct_db()
        for row in conn.execute("SELECT id, username, role FROM users WHERE active=1"):
            perms = ns.get_user_permissions(row["id"], row["role"])
            check(
                f"permissions user {row['username']}",
                ("view_admin" in perms) == is_admin_role(row["role"]),
                f"role={row['role']}",
            )
        conn.close()

    # Start Center section wiring
    from app.start_center import StartCenter

    sc = StartCenter.__new__(StartCenter)
    sections = StartCenter._define_sections(sc)
    for key, (label, items) in sections.items():
        for title, desc, cmd, tone in items:
            check(f"StartCenter.{key}.{title}", callable(cmd))

    # Required new modules on disk
    for rel in ("app/role_utils.py", "app/installer_auth.py", "app/emergency_access.py"):
        check(f"file {rel}", (LIVE / rel).exists() or (BASE / rel).exists())

    from app.emergency_access import ensure_mastery_key_on_owner_install, verify_emergency_access_setup

    target = LIVE if LIVE.exists() else BASE
    seeded, seed_msg = ensure_mastery_key_on_owner_install(target)
    check("owner mastery key ensured", seeded or "Worker client" in seed_msg, seed_msg)
    result = verify_emergency_access_setup(target)
    check("emergency access setup", bool(result.get("ok")), str(result.get("secrets_path", "")))

    print("---")
    if errors:
        print(f"FAILED {len(errors)} check(s)")
        for e in errors:
            print(" ", e)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
