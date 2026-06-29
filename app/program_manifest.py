"""Canonical file, script, and package manifest for JRC installs."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

APP_VERSION = "7.12.0 Secure Access & Account Verification Edition"

REQUIRED_PACKAGES = ("flask", "waitress", "reportlab", "gunicorn")

REQUIRED_DIRS = (
    "app",
    "assets",
    "data",
    "exports",
    "logs",
    "scripts",
    "backups",
    "evidence",
    "uploads",
    "file_sources",
    "business_standards",
    "chatgpt_imports",
)

ROOT_FILES = (
    "VERSION.txt",
    "requirements.txt",
    "ensure_venv.bat",
    "setup_runtime_env.bat",
    "Launch-JRC-Manager.bat",
    "run_jr_manager_hidden.vbs",
    "INSTALL_J_AND_R_MANAGER.vbs",
    "!!! START INSTALL HERE.vbs",
    "install_jr_job_manager_ui.ps1",
    "SYNC_LIVE_INSTALL.bat",
    "LIVE_FULL_UPDATE.vbs",
)

SCRIPT_FILES = (
    "scripts/Ensure-DesktopShortcuts.ps1",
    "scripts/Seed-OwnerEmergencyKey.ps1",
    "scripts/Resolve-InstallDir.ps1",
    "scripts/generate_shortcut_icons.py",
)

CORE_APP_FILES = (
    "app/start_center.py",
    "app/jr_job_manager.py",
    "app/network_server.py",
    "app/local_login_gate.py",
    "app/role_permissions.py",
    "app/application_notifications.py",
    "app/dashboard_config.py",
    "app/schema_migrations.py",
    "app/emergency_access.py",
    "app/emergency_routes.py",
    "app/startup_setup.py",
    "app/install_setup_log.py",
    "app/admin_developer_suite.py",
    "app/admin_db_editor.py",
    "app/live_full_update.py",
    "app/program_manifest.py",
)

VERIFY_SCRIPTS = (
    ("Sync Test", "app/_jrc_sync_test.py"),
    ("Emergency Access Check", "app/emergency_access_check.py"),
    ("Login/Install System Check", "app/login_install_system_check.py"),
    ("Permission View Check", "app/permission_view_check.py"),
    ("Final Program Verify", "app/final_program_verify.py"),
    ("System Check", "app/system_check.py"),
    ("Host Quick Test", "app/host_quick_test.py"),
)

DEVELOPER_TOOLS = (
    ("Full Live Update", "app/live_full_update.py", "Verify, sync, log, save report"),
    ("Self Setup + Verify", "app/self_setup_verify.py", "Post-install check bundle"),
    ("Emergency Access Check", "app/emergency_access_check.py", "Mastery key + all roles"),
    ("Sync Test", "app/_jrc_sync_test.py", "Role and Start Center wiring"),
    ("Extreme Final Verify", "app/extreme_final_verify.py", "Deep QA sweep"),
    ("Background Troubleshooter", "app/background_troubleshooter.py", "Auto repair report"),
    ("Admin Security Final Check", "app/admin_security_final_check.py", "Default password policy"),
    ("Security Perspective Audit", "app/security_perspective_audit.py", "Security review"),
    ("Access Mode Check", "app/access_mode_check.py", "Access modes"),
    ("Dashboard Role Check", "app/dashboard_role_check.py", "Dashboard by role"),
    ("Cloud Deploy Check", "app/cloud_deploy_check.py", "Cloud files"),
    ("v6 Final Readiness", "app/v6_final_readiness.py", "Readiness bundle"),
    ("Live Deployment Readiness", "app/live_deployment_readiness.py", "Deploy checklist"),
    ("Internet Cloud Security Verify", "app/internet_cloud_security_verify.py", "Cloud security"),
    ("Initialize Install", "app/initialize_install.py", "Trusted device + install init"),
    ("Dependency Repair", "app/dependency_tools.py", "pip install requirements"),
    ("Auto Host Repair", "app/auto_host_repair.py", "Host repair"),
    ("Full Program QA", "app/full_program_qa.py", "Full QA"),
)


def verify_layout(base_dir: Path) -> Tuple[List[str], List[str], List[str]]:
    base = Path(base_dir).resolve()
    missing: List[str] = []
    warnings: List[str] = []
    ok: List[str] = []

    for d in REQUIRED_DIRS:
        p = base / d
        if p.exists():
            ok.append(f"dir:{d}")
        elif d in ("app", "scripts", "data", "logs"):
            missing.append(f"dir:{d}")
        else:
            warnings.append(f"dir:{d} (will be created)")

    for rel in ROOT_FILES + SCRIPT_FILES + CORE_APP_FILES:
        p = base / rel
        if p.exists():
            ok.append(rel)
        else:
            missing.append(rel)

    version = base / "VERSION.txt"
    if version.exists() and APP_VERSION.split()[0] not in version.read_text(encoding="utf-8", errors="replace"):
        warnings.append(f"VERSION.txt may be stale (expected {APP_VERSION})")

    return ok, missing, warnings


def package_status() -> Dict[str, bool]:
    import importlib.util

    return {name: importlib.util.find_spec(name) is not None for name in REQUIRED_PACKAGES}
