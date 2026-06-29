"""First-run installer initializer for J and R Construction Manager."""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.jr_job_manager import DB_PATH, Database, get_device_id, iso_now
from app.role_utils import DEFAULT_OWNER_USERNAME


def main() -> int:
    db = Database(DB_PATH)
    device = get_device_id()
    db.set_setting("trusted_admin_device_id", device)
    db.set_setting("owner", "Jacob Cosentino")
    db.log("Install", f"Install initializer ran. Trusted administrator device ID: {device}")
    try:
        from app.install_setup_log import log_event, mark_step

        log_event(BASE_DIR, "InstallInit", f"Trusted device registered {device}")
        mark_step(BASE_DIR, "runtime_setup", "ok", "Install initializer completed")
    except Exception:
        pass
    db.conn.close()
    print("J and R Construction Manager initialized.")
    print(f"Trusted administrator device ID: {device}")
    print(f"Default first-setup login on this PC: {DEFAULT_OWNER_USERNAME} / (set during install wizard)")
    print("Security note: change the default password immediately after first login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
