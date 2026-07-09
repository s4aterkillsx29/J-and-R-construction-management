# -*- coding: utf-8 -*-
"""UI dashboard final check — Start Center + web admin/home dashboards."""
from __future__ import annotations

import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
APP = BASE / "app"
EXPORTS = BASE / "exports"


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    ok: list[str] = []

    sc = (APP / "start_center.py").read_text(encoding="utf-8", errors="replace")
    sb = (APP / "startup_bootstrap.py").read_text(encoding="utf-8", errors="replace")
    ns = (APP / "network_server.py").read_text(encoding="utf-8", errors="replace")
    dc = (APP / "dashboard_config.py").read_text(encoding="utf-8", errors="replace")

    try:
        from app.program_manifest import APP_VERSION
    except Exception:
        APP_VERSION = "unknown"

    checks = {
        "Start Center scrollable canvas": "tk.Canvas" in sc and "yscrollcommand" in sc,
        "Start Center blocking login": "require_blocking_login" in sb or "startup_bootstrap" in sc,
        "Web action-grid CSS": ".action-grid" in ns and "grid-template-columns:repeat(auto-fit" in ns,
        "Unified dashboard tiles module": "render_dashboard_sections" in dc and "dashboard_tiles" in dc,
        "Admin command center": "Owner Admin Command Center" in ns,
        "Admin pending account requests table": "Pending Account Requests" in ns,
        "Admin inline account type change": "_admin_user_role_cell" in ns and "quick_change_user_role" in ns,
        "Customer dashboard limited": "Customer privacy" in ns and "customer_portal" in dc,
        "External dashboard limited": "External Dashboard" in ns,
        "Global login gate": "enforce_global_login_required" in ns,
        "Admin hub nav item": "Admin Hub" in dc,
        "Worker applications tile": "Worker Applications" in dc or "/applications" in ns,
        "Live chat in nav": "Live Chat" in dc,
        "File access security": "file_access_security" in ns,
        "Version in network server": APP_VERSION.split()[0] in ns,
    }
    for name, passed in checks.items():
        (ok if passed else errors).append(name)

    if "7.9.0" in sc:
        warnings.append("Start Center APP_VERSION still shows 7.9.0 — cosmetic only")

    EXPORTS.mkdir(exist_ok=True)
    out = EXPORTS / f"JRC_UI_Dashboard_Final_Check_{time.strftime('%Y-%m-%d_%H%M%S')}.txt"
    lines = [
        "JRC UI Dashboard Final Check",
        time.strftime("%Y-%m-%d %H:%M:%S"),
        f"Expected program version: {APP_VERSION}",
        "",
        "OK:",
    ]
    lines += [f"  - {x}" for x in ok]
    lines += ["", "WARNINGS:"] + ([f"  - {x}" for x in warnings] or ["  - None"])
    lines += ["", "ERRORS:"] + ([f"  - {x}" for x in errors] or ["  - None"])
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
