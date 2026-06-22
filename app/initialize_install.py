"""First-run installer initializer for J and R Construction Manager."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from jr_job_manager import Database, DB_PATH, get_device_id, iso_now


def main() -> int:
    db = Database(DB_PATH)
    device = get_device_id()
    db.set_setting("trusted_admin_device_id", device)
    db.set_setting("owner", "Jacob Cosentino")
    db.log("Install", f"Install initializer ran. This local PC/device ID is registered as trusted administrator device: {device}")
    db.conn.close()
    print("J and R Construction Manager initialized.")
    print(f"Trusted administrator device ID: {device}")
    print("Default login: admin / admin")
    print("Security note: change the default password after first login.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
