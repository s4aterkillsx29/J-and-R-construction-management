"""Save a program update record to journal, exports, and INSTALL_SETUP_REPORT.txt."""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

PASSWORD_POLICY_CHANGES = [
    "Password minimum length is 8 for all roles (owner/admin included).",
    "Symbols are optional; uppercase, lowercase, and a digit are required.",
    "Removed hidden owner entropy bar (3.5) that blocked normal 8-character passwords.",
    "Web admin change-password page shows correct policy text via password_policy_summary().",
    "Account Database Editor and register forms use matching placeholders.",
    "Live update sync includes Documents\\JRC\\J-and-R-construction-management install path.",
]

PASSWORD_POLICY_NOTES = [
    "Restart the local host after updates so Flask reloads densus_policy.py.",
    "Example valid owner password after fix: Abcd1xyz or Work8Day.",
    "Forbidden defaults (ivygrows, admin123, etc.) remain blocked unless mastery key is used.",
]

ADMIN_DB_CHANGES = [
    "Account Database Editor hub at /admin/database/accounts.",
    "Start Center: Account Database Editor in Admin & security and Admin Panel strip.",
    "Admin web panel links: Account DB and All Tables.",
]


def save_password_policy_update() -> int:
    from app.install_setup_log import record_program_update
    from app.live_full_update import live_install_dirs
    from app.program_manifest import APP_VERSION

    title = "Password policy + admin database editor update"
    changes = PASSWORD_POLICY_CHANGES + ADMIN_DB_CHANGES
    notes = PASSWORD_POLICY_NOTES + [f"Recorded at version {APP_VERSION}."]

    targets = live_install_dirs()
    if BASE_DIR not in targets:
        targets = [BASE_DIR] + [t for t in targets if t.resolve() != BASE_DIR.resolve()]

    print(f"Saving update record — {APP_VERSION}")
    print(f"Targets: {len(targets)}")
    for target in targets:
        if not target.exists():
            print(f"  [SKIP] missing {target}")
            continue
        paths = record_program_update(target, title, changes, version=APP_VERSION, notes=notes)
        print(f"  [OK] {target}")
        print(f"       Export: {paths['export']}")
        print(f"       Latest: {paths['latest']}")
        print(f"       Journal: {paths['journal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(save_password_policy_update())
