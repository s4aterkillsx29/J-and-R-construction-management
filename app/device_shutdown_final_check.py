# -*- coding: utf-8 -*-
"""Verify remember-device policy and shutdown/log persistence for live use."""
from __future__ import annotations

import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
APP = BASE / "app"


def main() -> int:
    errors: list[str] = []
    ok: list[str] = []

    ns = (APP / "network_server.py").read_text(encoding="utf-8", errors="replace")
    hp = (APP / "host_process.py").read_text(encoding="utf-8", errors="replace")
    sl = (APP / "server_lifecycle.py").read_text(encoding="utf-8", errors="replace")
    isl = (APP / "install_setup_log.py").read_text(encoding="utf-8", errors="replace")
    sc = (APP / "start_center.py").read_text(encoding="utf-8", errors="replace")

    checks = {
        "Remember device checkbox on login": "remember_device" in ns and "Remember this PC/phone for 90 days" in ns,
        "Device cookie HttpOnly + SameSite": "httponly=True" in ns and "samesite" in ns.lower(),
        "90-day device expiry": "DEVICE_COOKIE_MAX_AGE_SECONDS" in ns and "90" in ns,
        "Device fingerprint hashed (not raw token)": "_hash_device_token" in ns and "SHA-256" in ns or "sha256" in ns.lower(),
        "Known devices admin page": "/admin/devices" in ns and "known_devices" in ns,
        "Forget this device route": "/forget-this-device" in ns,
        "Graceful shutdown handlers": "register_shutdown_handlers" in ns and "atexit.register" in sl,
        "Pre-shutdown backup": "create_pre_shutdown_backup" in sl,
        "Shutdown log snapshots": "export_log_snapshots" in sl,
        "Session archive on maintenance": "snapshot_sessions" in (APP / "data_pipeline.py").read_text(encoding="utf-8"),
        "Prepare-shutdown API (localhost)": "/api/host/prepare-shutdown" in ns,
        "Stop host calls graceful shutdown": "_request_graceful_shutdown" in hp,
        "Stop host safety backup fallback": "_run_local_shutdown_safety_net" in hp,
        "Install journal fsync": "fsync" in isl,
        "Start Center stop mentions auto-save": "auto-saved on shutdown" in sc,
        "Owner login copy admin/ivygrows": "admin / ivygrows" in ns,
        "Trusted admin device registration": "trusted_admin_device_id" in ns,
        "Master owner PC registration": "register_master_owner_device" in ns,
    }
    for name, passed in checks.items():
        (ok if passed else errors).append(name)

    EXPORTS = BASE / "exports"
    EXPORTS.mkdir(exist_ok=True)
    out = EXPORTS / f"JRC_Device_Shutdown_Final_Check_{time.strftime('%Y-%m-%d_%H%M%S')}.txt"
    lines = [
        "JRC Device Remember + Shutdown Log Final Check",
        time.strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "OK:",
    ]
    lines += [f"  - {x}" for x in ok]
    lines += ["", "ERRORS:"] + ([f"  - {x}" for x in errors] or ["  - None"])
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
