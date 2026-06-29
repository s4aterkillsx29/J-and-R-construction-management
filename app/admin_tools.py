"""Admin command-center helpers — host repair, troubleshooter, status."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"


def get_admin_dashboard_status() -> Dict[str, Any]:
    import os
    from app.troubleshooter_engine import check_host_endpoints

    port = int(os.environ.get("JRC_PORT", "8765"))
    status: Dict[str, Any] = {"port": port, "checks": []}
    try:
        from app.launcher_repair import verify_app_imports
        ok, msg = verify_app_imports()
        status["module_ok"] = ok
        status["module_message"] = msg
    except Exception as exc:
        status["module_ok"] = False
        status["module_message"] = str(exc)

    try:
        host = check_host_endpoints()
        status["host_status"] = host.status
        status["host_detail"] = host.detail
    except Exception:
        status["host_status"] = "WARN"
        status["host_detail"] = "Could not check host."

    try:
        from app.densus_bridge import densus_installed
        status["densus_installed"] = densus_installed()
    except Exception:
        status["densus_installed"] = False

    db = BASE_DIR / "data" / "jr_business.db"
    status["database_exists"] = db.exists()

    reports = sorted(EXPORT_DIR.glob("JRC_Full_Troubleshooter_*.txt"), reverse=True)
    status["last_report"] = reports[0].name if reports else ""
    return status


def get_host_status() -> Dict[str, Any]:
    return get_admin_dashboard_status()


def run_auto_repair_sequence() -> Dict[str, Any]:
    from app.troubleshooter_engine import run_full_troubleshoot

    report_path, steps = run_full_troubleshoot(repair=True)
    return {
        "steps": [(s.status, f"{s.category} / {s.name}", s.detail) for s in steps],
        "report_path": str(report_path),
    }


def format_repair_summary(results: Dict[str, Any]) -> str:
    lines = ["J & R Construction Manager — Admin Auto-Repair", ""]
    for level, component, message in results.get("steps", []):
        lines.append(f"[{level}] {component}")
        lines.append(f"  {message[:600]}")
        lines.append("")
    if results.get("report_path"):
        lines.append(f"Full report: {results['report_path']}")
    return "\n".join(lines)
