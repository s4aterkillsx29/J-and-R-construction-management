"""
J & R Construction Manager — unified troubleshooter with safe auto-repairs.
Covers: launchers, venv, database, folders, shortcuts, host, payments, pipeline, Densus, health.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "jr_business.db"

REQUIRED_DIRS = ("data", "logs", "exports", "backups", "evidence", "chatgpt_imports", "data/densus_admin")


@dataclass
class TroubleStep:
    category: str
    name: str
    status: str  # OK, WARN, ERROR, FIXED, SKIP
    detail: str
    repaired: bool = False


def _python_exe() -> str:
    venv = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def _run_module(module: str, timeout: int = 180) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            [_python_exe(), "-m", module],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode, out.strip()
    except Exception as exc:
        return 1, str(exc)


def _pip_install_requirements() -> Tuple[bool, str]:
    req = BASE_DIR / "requirements.txt"
    if not req.exists():
        return False, "requirements.txt missing"
    try:
        proc = subprocess.run(
            [_python_exe(), "-m", "pip", "install", "-r", str(req)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        msg = (proc.stdout or proc.stderr or "").strip()[-1200:]
        return proc.returncode == 0, msg or f"pip exit {proc.returncode}"
    except Exception as exc:
        return False, str(exc)


def repair_folders() -> TroubleStep:
    created = []
    for name in REQUIRED_DIRS:
        p = BASE_DIR / name
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(name)
    if created:
        return TroubleStep("Folders", "Required directories", "FIXED", f"Created: {', '.join(created)}", True)
    return TroubleStep("Folders", "Required directories", "OK", "All required folders exist.")


def check_launchers(repair: bool = True) -> List[TroubleStep]:
    steps: List[TroubleStep] = []
    try:
        from app.launcher_repair import repair_launcher_files, verify_app_imports
        if repair:
            actions = repair_launcher_files(BASE_DIR)
            if actions:
                steps.append(TroubleStep("Launchers", "Module mode scripts", "FIXED", "; ".join(actions[:4]), True))
            else:
                steps.append(TroubleStep("Launchers", "Module mode scripts", "OK", "Launchers already correct."))
        ok, msg = verify_app_imports(BASE_DIR)
        steps.append(TroubleStep("Launchers", "Python imports", "OK" if ok else "ERROR", msg))
    except Exception as exc:
        steps.append(TroubleStep("Launchers", "Launcher repair", "ERROR", str(exc)))
    return steps


def check_dependencies(repair: bool = True) -> List[TroubleStep]:
    steps: List[TroubleStep] = []
    import importlib.util
    for mod in ("flask", "waitress", "reportlab"):
        ok = importlib.util.find_spec(mod) is not None
        if ok:
            steps.append(TroubleStep("Dependencies", mod, "OK", f"{mod} installed."))
        else:
            steps.append(TroubleStep("Dependencies", mod, "WARN", f"{mod} missing — network/PDF features need it."))
    missing = [s.name for s in steps if s.status == "WARN"]
    if missing and repair:
        ok, msg = _pip_install_requirements()
        steps.append(TroubleStep("Dependencies", "pip install", "FIXED" if ok else "ERROR", msg[:500], ok))
        for mod in missing:
            if importlib.util.find_spec(mod):
                steps.append(TroubleStep("Dependencies", f"{mod} (after pip)", "OK", "Installed."))
    return steps


def check_database(repair: bool = True) -> List[TroubleStep]:
    steps: List[TroubleStep] = []
    if not DB_PATH.exists():
        steps.append(TroubleStep("Database", "jr_business.db", "SKIP", "No database yet — normal on fresh worker client."))
        return steps
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("SELECT 1").fetchone()
            steps.append(TroubleStep("Database", "Open database", "OK", str(DB_PATH)))
            qc = conn.execute("PRAGMA quick_check").fetchone()[0]
            if str(qc).lower() == "ok":
                steps.append(TroubleStep("Database", "Integrity quick_check", "OK", "Passed."))
            else:
                steps.append(TroubleStep("Database", "Integrity quick_check", "ERROR", str(qc)))
            if repair:
                try:
                    from app.payment_system import ensure_payment_schema
                    ensure_payment_schema(conn)
                    steps.append(TroubleStep("Database", "Payment schema", "FIXED", "Payment tables verified/updated.", True))
                except Exception as exc:
                    steps.append(TroubleStep("Database", "Payment schema", "WARN", str(exc)))
    except Exception as exc:
        steps.append(TroubleStep("Database", "Database", "ERROR", str(exc)))
    return steps


def check_shortcuts(repair: bool = True) -> TroubleStep:
    ps1 = BASE_DIR / "scripts" / "Ensure-DesktopShortcuts.ps1"
    if not ps1.exists():
        return TroubleStep("Shortcuts", "Desktop shortcuts", "SKIP", "Script not found.")
    if not repair:
        return TroubleStep("Shortcuts", "Desktop shortcuts", "OK", "Repair skipped (check only).")
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), "-InstallDir", str(BASE_DIR), "-Quiet"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (proc.stdout or proc.stderr or "").strip()[-400:]
        return TroubleStep(
            "Shortcuts", "Desktop shortcuts", "FIXED" if proc.returncode == 0 else "WARN",
            out or f"Exit {proc.returncode}", proc.returncode == 0,
        )
    except Exception as exc:
        return TroubleStep("Shortcuts", "Desktop shortcuts", "ERROR", str(exc))


def check_host_endpoints() -> TroubleStep:
    try:
        from app.auto_host_repair import get_saved_port, url_check
        port = get_saved_port()
        url = f"http://127.0.0.1:{port}/api/health"
        r = url_check(url)
        if r.get("ok"):
            return TroubleStep("Shared Host", "Health endpoint", "OK", f"Port {port} responding.")
        return TroubleStep("Shared Host", "Health endpoint", "WARN", f"Port {port} not responding — start host from Admin or Start Center.")
    except Exception as exc:
        return TroubleStep("Shared Host", "Health endpoint", "WARN", str(exc))


def check_pipeline(repair: bool = True) -> List[TroubleStep]:
    steps: List[TroubleStep] = []
    try:
        from app.data_pipeline import run_master_pipeline_maintenance, verify_pipelines
        for level, comp, msg in verify_pipelines():
            st = "OK" if level == "OK" else "WARN" if level in ("WARN", "INFO") else "ERROR"
            steps.append(TroubleStep("Pipeline", comp, st, msg))
        if repair:
            for line in run_master_pipeline_maintenance():
                steps.append(TroubleStep("Pipeline", "Maintenance", "FIXED", line, True))
    except Exception as exc:
        steps.append(TroubleStep("Pipeline", "Data pipeline", "WARN", str(exc)))
    return steps


def check_master_owner() -> TroubleStep:
    try:
        from app.master_owner import business_data_allowed_locally, is_master_owner_device
        return TroubleStep(
            "Owner PC",
            "Master owner device",
            "OK",
            f"Master={'yes' if is_master_owner_device() else 'no'}; local data={'yes' if business_data_allowed_locally() else 'no'}",
        )
    except Exception as exc:
        return TroubleStep("Owner PC", "Master owner", "WARN", str(exc))


def check_densus() -> TroubleStep:
    try:
        from app.densus_bridge import densus_installed, resolve_densus_install
        from app.densus_access import ensure_schema, pending_count, resolve_densus_package_source
        import sqlite3

        db_path = BASE_DIR / "data" / "jr_business.db"
        pending = 0
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            pending = pending_count(conn)
            conn.close()
        pkg = resolve_densus_package_source()
        if densus_installed():
            extra = f"Found at {resolve_densus_install()}"
            if pending:
                extra += f" | {pending} Densus access request(s) pending owner approval"
            return TroubleStep("Densus", "Desktop app", "OK", extra)
        if pkg:
            msg = f"Package source at {pkg} — install to Desktop after owner approves admin"
            if pending:
                msg += f" ({pending} pending approval)"
            return TroubleStep("Densus", "Desktop app", "WARN", msg)
        return TroubleStep(
            "Densus",
            "Desktop app",
            "WARN",
            "Not on Desktop. Admins need owner approval at /admin/densus before download.",
        )
    except Exception as exc:
        return TroubleStep("Densus", "Integration", "WARN", str(exc))


def run_module_tools(repair: bool = True) -> List[TroubleStep]:
    steps: List[TroubleStep] = []
    for label, mod in [("System check", "app.system_check"), ("Auto host repair", "app.auto_host_repair")]:
        code, out = _run_module(mod)
        st = "OK" if code == 0 else "WARN"
        steps.append(TroubleStep("Tools", label, st, (out or "(no output)")[-800:]))
    return steps


def run_full_troubleshoot(repair: bool = True) -> Tuple[Path, List[TroubleStep]]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = EXPORT_DIR / f"JRC_Full_Troubleshooter_{stamp}.txt"

    all_steps: List[TroubleStep] = []
    all_steps.append(repair_folders())
    all_steps.extend(check_launchers(repair))
    all_steps.extend(check_dependencies(repair))
    all_steps.extend(check_database(repair))
    all_steps.append(check_shortcuts(repair))
    all_steps.append(check_host_endpoints())
    all_steps.append(check_master_owner())
    all_steps.append(check_densus())
    all_steps.extend(check_pipeline(repair))
    all_steps.extend(run_module_tools(repair))

    # Optional: web health checks when Flask app context is active
    try:
        from flask import has_app_context
        if has_app_context():
            from app.network_server import run_health_checks
            for level, comp, msg in run_health_checks():
                all_steps.append(TroubleStep("Health", comp, level, msg, level == "FIXED"))
    except Exception:
        pass

    lines = [
        "J & R Construction Manager — Full Troubleshooter",
        f"Time: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"PC: {os.environ.get('COMPUTERNAME', '?')} | User: {os.environ.get('USERNAME', '?')}",
        f"Repair mode: {'ON' if repair else 'CHECK ONLY'}",
        "",
    ]
    counts = {"OK": 0, "FIXED": 0, "WARN": 0, "ERROR": 0, "SKIP": 0}
    for s in all_steps:
        counts[s.status] = counts.get(s.status, 0) + 1
        flag = " [REPAIRED]" if s.repaired else ""
        lines.append(f"[{s.status}] {s.category} / {s.name}{flag}")
        lines.append(f"    {s.detail}")
        lines.append("")
    lines.append(f"Summary: OK={counts.get('OK',0)} FIXED={counts.get('FIXED',0)} WARN={counts.get('WARN',0)} ERROR={counts.get('ERROR',0)}")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    summary_json = EXPORT_DIR / f"JRC_Full_Troubleshooter_{stamp}.json"
    summary_json.write_text(
        json.dumps([{"category": s.category, "name": s.name, "status": s.status, "detail": s.detail, "repaired": s.repaired} for s in all_steps], indent=2),
        encoding="utf-8",
    )
    return report_path, all_steps


def format_steps_html(steps: List[TroubleStep]) -> str:
    import html as html_mod
    rows = []
    for s in steps:
        badge = {"OK": "ok", "FIXED": "ok", "WARN": "yellow", "ERROR": "red", "SKIP": ""}.get(s.status, "")
        rep = " <span class='muted'>(auto-repaired)</span>" if s.repaired else ""
        rows.append(
            f"<tr><td><span class='badge {badge}'>{html_mod.escape(s.status)}</span></td>"
            f"<td>{html_mod.escape(s.category)}</td><td>{html_mod.escape(s.name)}{rep}</td>"
            f"<td class='muted'>{html_mod.escape(s.detail[:200])}</td></tr>"
        )
    return "".join(rows) or "<tr><td colspan='4'>No results yet. Run troubleshooter below.</td></tr>"
