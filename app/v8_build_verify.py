# -*- coding: utf-8 -*-
"""v8 full build verification — file manifest + all verify scripts + route smoke."""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
APP = BASE / "app"
EXPORTS = BASE / "exports"

# Master plan §18 + §21 required files (v8)
V8_REQUIRED_FILES = [
    "app/program_shell.py",
    "app/program_paths.py",
    "app/ui_actions.py",
    "app/pdf_bridge.py",
    "PROGRAM_BUSINESS_MANIFEST.json",
    "app/reliability/__init__.py",
    "app/reliability/guardian_scheduler.py",
    "app/reliability/guardian_store.py",
    "app/reliability/guardian_job_queue.py",
    "app/reliability/repair_policy.py",
    "app/reliability/consistency_audit.py",
    "app/reliability/guardian_report.py",
    "app/reliability/register_routes.py",
    "app/messenger/__init__.py",
    "app/messenger/schema.py",
    "app/messenger/permissions.py",
    "app/messenger/service.py",
    "app/messenger/register_routes.py",
    "app/mobile_platform/__init__.py",
    "app/mobile_platform/outbox_schema.py",
    "app/mobile_platform/outbox_processor.py",
    "app/mobile_platform/sync_on_online.py",
    "app/mobile_platform/register_routes.py",
    "app/mobile_platform/feature_matrix.json",
    "app/routes/log_events.py",
    "app/office_ai/ai_viability_matrix.json",
    "app/office_ai/tools/generate_office_brief.py",
    "app/office_ai/tools/run_consistency_audit.py",
    "static/messenger.css",
    "static/messenger.js",
    "static/admin-live-sessions.js",
    "Launch-JRC-Manager.bat",
    "tests/test_path_separation.py",
    "tests/test_guardian_light.py",
    "tests/test_program_shell.py",
    "tests/test_messenger_permissions.py",
    "tests/test_mobile_outbox.py",
    "tests/test_mobile_permissions.py",
    "templates/messenger/drawer.html",
    "static/mobile/mobile-outbox.js",
    "static/mobile/mobile-app.js",
    "static/mobile/mobile-sw.js",
    "app/mobile_shell.py",
    "app/office_ai/context_packs/admin.json",
    "app/office_ai/context_packs/office_mgmt.json",
    "app/office_ai/context_packs/quote.json",
    "app/office_ai/context_packs/guardian.json",
    "app/office_ai/tools/admin_summarize_pending_accounts.py",
    "app/office_ai/tools/admin_recommend_account_role.py",
    "app/office_ai/tools/admin_review_user_permissions.py",
    "app/office_ai/tools/admin_audit_active_sessions.py",
    "app/office_ai/tools/admin_propose_access_change.py",
    "app/office_ai/tools/admin_run_security_audit.py",
    "app/office_ai/tools/office_mgmt_triage_todo_list.py",
    "app/office_ai/tools/office_mgmt_check_tax_savings_plan.py",
    "app/office_ai/tools/office_mgmt_draft_log_entry.py",
    "app/office_ai/tools/office_mgmt_follow_up_leads.py",
    "app/office_ai/tools/office_mgmt_triage_inbox_photos.py",
    "app/office_ai/tools/office_mgmt_update_dashboard_note.py",
    "app/office_ai/tools/quote_read_internal_workup.py",
    "app/office_ai/tools/quote_read_similar_jobs.py",
    "app/office_ai/tools/quote_draft_quote_scope.py",
    "app/office_ai/tools/quote_calculate_job_costing.py",
    "app/office_ai/tools/quote_build_quote_package.py",
    "app/office_ai/tools/quote_compare_quote_to_sent.py",
]

VERIFY_MODULES = [
    "app.system_check",
    "app.login_install_system_check",
    "app.permission_view_check",
    "app.final_program_verify",
    "app.ui_dashboard_final_check",
    "app.office_ai_verification_check",
    "app.account_request_verification_check",
    "app.file_access_security",
    "app.device_shutdown_final_check",
    "app.business_sources_security_audit",
    "app.live_release_verify",
]

ROUTE_SMOKE = [
    "/login",
    "/api/health",
    "/mobile/ping",
    "/admin/reliability",
    "/admin/command-center",
    "/admin/live-sessions",
    "/admin/ai-viability",
    "/log-event",
    "/api/mobile/status",
]


def _log(lines: list[str], msg: str, *, ok: bool | None = None) -> None:
    prefix = "OK" if ok is True else ("FAIL" if ok is False else "INFO")
    line = f"[{prefix}] {msg}"
    lines.append(line)
    print(line)


def check_files(lines: list[str]) -> int:
    errors = 0
    for rel in V8_REQUIRED_FILES:
        p = BASE / rel.replace("/", os.sep)
        if p.is_file():
            _log(lines, f"FILE {rel}", ok=True)
        else:
            _log(lines, f"FILE MISSING {rel}", ok=False)
            errors += 1
    return errors


def check_imports(lines: list[str]) -> int:
    errors = 0
    modules = [
        "app.program_shell",
        "app.program_paths",
        "app.ui_actions",
        "app.pdf_bridge",
        "app.reliability.guardian_scheduler",
        "app.messenger.permissions",
        "app.mobile_platform.outbox_processor",
        "app.routes.log_events",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
            _log(lines, f"IMPORT {mod}", ok=True)
        except Exception as exc:
            _log(lines, f"IMPORT {mod}: {exc}", ok=False)
            errors += 1
    return errors


def run_unittests(lines: list[str]) -> int:
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=str(BASE),
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        _log(lines, "unittest discover: PASS", ok=True)
    else:
        _log(lines, f"unittest discover: FAIL\n{r.stdout}\n{r.stderr}", ok=False)
    return r.returncode


def run_verify_scripts(lines: list[str]) -> int:
    errors = 0
    for mod in VERIFY_MODULES:
        r = subprocess.run([sys.executable, "-m", mod], cwd=str(BASE), capture_output=True, text=True)
        tail = (r.stdout or r.stderr or "")[-500:]
        if r.returncode == 0:
            _log(lines, f"VERIFY {mod}: exit 0", ok=True)
        else:
            _log(lines, f"VERIFY {mod}: exit {r.returncode} — {tail}", ok=False)
            errors += 1
    return errors


def route_smoke_test(lines: list[str]) -> int:
    errors = 0
    os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        for d in ("data", "exports", "evidence", "chatgpt_imports", "backups"):
            (base / d).mkdir()
        env_keys = {
            "JRC_DATA_DIR": str(base / "data"),
            "JRC_EXPORT_DIR": str(base / "exports"),
            "JRC_EVIDENCE_DIR": str(base / "evidence"),
            "JRC_CHATGPT_IMPORTS_DIR": str(base / "chatgpt_imports"),
            "JRC_BACKUP_DIR": str(base / "backups"),
            "JRC_DB_PATH": str(base / "data" / "jr_business.db"),
            "JRC_PORT": "8765",
            "JRC_ALLOW_LOCAL_DEFAULT_ADMIN": "1",
        }
        old = {k: os.environ.get(k) for k in env_keys}
        try:
            os.environ.update(env_keys)
            import sitecustomize

            sitecustomize._repair()
            ns = importlib.import_module("app.network_server")
            ns = importlib.reload(ns)
            ns.init_db()
            with ns.app.app_context():
                client = ns.app.test_client()
                for path in ROUTE_SMOKE:
                    resp = client.get(path)
                    if resp.status_code >= 500:
                        _log(lines, f"ROUTE {path} -> {resp.status_code}", ok=False)
                        errors += 1
                    else:
                        _log(lines, f"ROUTE {path} -> {resp.status_code}", ok=True)
        except Exception as exc:
            _log(lines, f"ROUTE smoke setup failed: {exc}", ok=False)
            errors += 1
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return errors


def main() -> int:
    lines: list[str] = [
        "J & R Construction Manager — v8 Full Build Verification",
        time.strftime("%Y-%m-%d %H:%M:%S"),
        "",
    ]
    try:
        from app.program_manifest import APP_VERSION

        lines.append(f"Version: {APP_VERSION}")
    except Exception:
        lines.append("Version: unknown")
    lines.append("")

    total_errors = 0
    total_errors += check_files(lines)
    lines.append("")
    total_errors += check_imports(lines)
    lines.append("")
    total_errors += run_unittests(lines)
    lines.append("")
    total_errors += run_verify_scripts(lines)
    lines.append("")
    total_errors += route_smoke_test(lines)
    lines.append("")
    lines.append(f"TOTAL ERRORS: {total_errors}")
    lines.append("OVERALL: PASS" if total_errors == 0 else "OVERALL: NEEDS ATTENTION")

    EXPORTS.mkdir(exist_ok=True)
    out = EXPORTS / f"JRC_V8_Full_Build_Verify_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    text = "\n".join(lines)
    out.write_text(text, encoding="utf-8")
    print(f"\nReport: {out}")

    try:
        from app.program_paths import program_docs_dir

        dest = program_docs_dir() / "exports"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / out.name).write_text(text, encoding="utf-8")
    except Exception:
        pass

    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
