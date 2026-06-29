# -*- coding: utf-8 -*-
"""Run all phase verification checks after live update."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def run_phase_verification(base_dir: Path | None = None) -> tuple[int, Path]:
    base = Path(base_dir or BASE_DIR).resolve()
    os.environ["JRC_DATA_DIR"] = str(base / "data")
    os.environ["JRC_DB_PATH"] = str(base / "data" / "jr_business.db")
    os.environ["JRC_LIVE_DIR"] = str(base)
    os.environ.setdefault("JRC_DROPBOX_RECORDS", "")

    lines = [
        "J & R CONSTRUCTION MANAGER — PHASE VERIFICATION REPORT",
        "=" * 62,
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Install: {base}",
        "",
    ]
    errors = 0

    # Phase 0 — layout + packages
    try:
        from app.program_manifest import APP_VERSION, package_status, verify_layout

        lines.append(f"VERSION: {APP_VERSION}")
        ok_files, missing, warnings = verify_layout(base)
        lines.append(f"Manifest: {len(ok_files)} OK, {len(missing)} missing, {len(warnings)} warnings")
        for m in missing:
            lines.append(f"  [MISSING] {m}")
            errors += 1
        pkgs = package_status()
        for name, ok in pkgs.items():
            if not ok:
                lines.append(f"  [PKG MISSING] {name}")
                errors += 1
        lines.append("")
    except Exception as exc:
        lines.append(f"Manifest check failed: {exc}")
        errors += 1

    # Phase 0 — system check
    lines.append("SYSTEM CHECK")
    try:
        import app.system_check as sc

        sc.BASE_DIR = base
        sc.DATA_DIR = base / "data"
        sc.DB = sc.DATA_DIR / "jr_business.db"
        sc.APP_DIR = base / "app"
        sc.REPORT_DIR = base / "exports"
        results = []
        code = sc.run()
        # run() prints and writes report; re-read latest report if needed
        lines.append(f"  system_check exit code: {code}")
        lines.append("")
    except Exception as exc:
        lines.append(f"  System check failed: {exc}")
        errors += 1

    # Phase 1-2 — office sync
    lines.append("OFFICE RECORDS SYNC (Phases 1-2)")
    try:
        from app.office_records_sync import run_office_sync

        rep = run_office_sync(base)
        lines.append(f"  dropbox-records: {rep.get('dropbox_records', 'NOT FOUND')}")
        for e in rep.get("errors") or []:
            lines.append(f"  [ERROR] {e}")
            errors += 1
        lines.append(f"  jobs inserted: {rep.get('jobs_inserted', 0)}")
        lines.append(f"  jobs updated: {rep.get('jobs_updated', 0)}")
        lines.append(f"  payroll import rows: {rep.get('payroll_rows_imported', 0)}")
        lines.append(f"  payroll export rows: {rep.get('payroll_rows_exported', 0)}")
        lines.append(f"  payroll merged to office: {rep.get('payroll_rows_merged', 0)}")
        lines.append(f"  income import rows: {rep.get('income_rows_imported', 0)}")
        lines.append(f"  income export rows: {rep.get('income_rows_exported', 0)}")
        lines.append(f"  income merged to office: {rep.get('income_rows_merged', 0)}")
        for n in rep.get("notes") or []:
            lines.append(f"  {n}")
        lines.append("")
    except Exception as exc:
        lines.append(f"  Office sync failed: {exc}")
        errors += 1

    # Phase 3 — data pipeline
    lines.append("DATA PIPELINE")
    try:
        from app.data_pipeline import get_data_mode, verify_pipelines, write_pipeline_manifest

        mode = get_data_mode()
        write_pipeline_manifest()
        lines.append(f"  mode: {mode}")
        for level, component, detail in verify_pipelines():
            lines.append(f"  [{level}] {component}: {detail}")
            if level == "ERROR":
                errors += 1
        lines.append("")
    except Exception as exc:
        lines.append(f"  Pipeline check: {exc} (non-fatal)")
        lines.append("")

    # Phase 4 — syntax verify
    lines.append("FINAL PROGRAM VERIFY (syntax/routes)")
    try:
        import py_compile

        for py in sorted((base / "app").glob("*.py")):
            py_compile.compile(str(py), doraise=True)
        lines.append(f"  Python syntax OK: {len(list((base / 'app').glob('*.py')))} modules")
        lines.append("")
    except Exception as exc:
        lines.append(f"  Syntax error: {exc}")
        errors += 1

    # Phase 5 — login/install system check
    lines.append("LOGIN / INSTALL SYSTEM CHECK")
    try:
        import subprocess

        proc = subprocess.run(
            [sys.executable, "-m", "app.login_install_system_check"],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=120,
        )
        lines.append(f"  exit code: {proc.returncode}")
        if proc.returncode != 0:
            errors += 1
            for ln in (proc.stdout or "").splitlines()[-15:]:
                if ln.strip().startswith("-") or "ERROR" in ln:
                    lines.append(f"    {ln.strip()}")
        lines.append("")
    except Exception as exc:
        lines.append(f"  login_install_system_check failed: {exc}")
        errors += 1

    # Phase 6 — customer portal security check
    lines.append("CUSTOMER PORTAL / PERMISSIONS CHECK")
    try:
        import subprocess

        proc = subprocess.run(
            [sys.executable, "-m", "app.customer_request_final_check"],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=120,
        )
        lines.append(f"  exit code: {proc.returncode}")
        if proc.returncode != 0:
            errors += 1
            for ln in (proc.stdout or "").splitlines():
                if ln.startswith("ERROR"):
                    lines.append(f"    {ln}")
        else:
            lines.append("  customer portal static checks: PASS")
        ns = (base / "app" / "network_server.py").read_text(encoding="utf-8", errors="ignore")
        if "api_mobile_jobs" in ns and "is_customer_or_external" in ns:
            lines.append("  mobile API customer guards: present")
        else:
            lines.append("  [WARN] mobile API customer guards may be missing")
        if "densus_jrc_admin" in (base / "app" / "densus_routes.py").read_text(encoding="utf-8", errors="ignore"):
            lines.append("  Densus JRC admin hub: present")
        if (base / "app" / "densus_access.py").exists():
            lines.append("  Densus owner-approval access module: present")
        else:
            lines.append("  [MISSING] app/densus_access.py")
            errors += 1
        lines.append("")
    except Exception as exc:
        lines.append(f"  customer check failed: {exc}")
        errors += 1

    # Phase 7 — troubleshooter (read-only summary)
    lines.append("TROUBLESHOOTER ENGINE")
    try:
        import app.troubleshooter_engine as te

        te.BASE_DIR = base
        te.DATA_DIR = base / "data"
        te.DB_PATH = te.DATA_DIR / "jr_business.db"
        te.EXPORT_DIR = base / "exports"
        te.LOG_DIR = base / "logs"
        steps = te.run_full_troubleshoot(repair=False)
        if isinstance(steps, tuple):
            _, step_list = steps
        else:
            step_list = steps
        bad = [s for s in step_list if s.status in ("ERROR", "WARN")]
        lines.append(f"  steps: {len(step_list)} | issues: {len(bad)}")
        for s in bad[:12]:
            lines.append(f"  [{s.status}] {s.category}/{s.name}: {s.detail[:120]}")
            if s.status == "ERROR":
                errors += 1
        lines.append("")
    except Exception as exc:
        lines.append(f"  troubleshooter: {exc} (non-fatal)")
        lines.append("")

    # Phase 8 — live release verify (DB alignment, standards, chat UI)
    lines.append("LIVE RELEASE VERIFY")
    try:
        from app.live_release_verify import run_live_release_verify

        lr_errors, lr_report = run_live_release_verify(base)
        lines.append(f"  report: {lr_report.name}")
        if lr_errors:
            errors += lr_errors
            lines.append(f"  live_release_verify: {lr_errors} error(s)")
        else:
            lines.append("  live_release_verify: PASS")
        lines.append("")
    except Exception as exc:
        lines.append(f"  live_release_verify failed: {exc}")
        errors += 1

    # Phase 9 — account request + file access security
    lines.append("ACCOUNT REQUEST + FILE ACCESS SECURITY")
    try:
        import subprocess

        for mod in ("app.account_request_verification_check", "app.file_access_security", "app.ui_dashboard_final_check"):
            proc = subprocess.run(
                [sys.executable, "-m", mod, str(base)],
                cwd=str(base),
                capture_output=True,
                text=True,
                timeout=120,
            )
            lines.append(f"  {mod}: exit {proc.returncode}")
            if proc.returncode != 0:
                errors += 1
                for ln in (proc.stdout or "").splitlines():
                    if "ERROR" in ln:
                        lines.append(f"    {ln.strip()}")
        lines.append("")
    except Exception as exc:
        lines.append(f"  security checks failed: {exc}")
        errors += 1

    lines.append(f"SUMMARY: {errors} error(s)")
    lines.append("PASS" if errors == 0 else "NEEDS ATTENTION")

    report = base / "exports" / f"JRC_Phase_Verification_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    (base / "PHASE_VERIFICATION_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport: {report}")
    return errors, report


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR
    code, _ = run_phase_verification(base)
    return 1 if code else 0


if __name__ == "__main__":
    raise SystemExit(main())
