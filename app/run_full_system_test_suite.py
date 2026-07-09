# -*- coding: utf-8 -*-
"""J & R Construction Manager — full system test suite.

Run anytime to verify the install, database, web host, security, Office AI,
and integration layers. Writes a plain-English report to exports/.

Usage:
    python -m app.run_full_system_test_suite              # standard (recommended)
    python -m app.run_full_system_test_suite --quick      # fast daily check
    python -m app.run_full_system_test_suite --full       # everything (~10-15 min)
    python -m app.run_full_system_test_suite --with-host  # also probe live host port

See docs/SYSTEM_TEST_SUITE_GUIDE.md for full instructions.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"


@dataclass
class CheckResult:
    name: str
    stage: str
    status: str  # PASS | FAIL | WARN | SKIP
    seconds: float
    detail: str = ""
    exit_code: Optional[int] = None


@dataclass
class SuiteReport:
    mode: str
    started: str
    finished: str
    base_dir: str
    python: str
    version: str = ""
    results: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.status == "WARN")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "SKIP")


def _setup_env(base: Path) -> None:
    os.environ.setdefault("JRC_DATA_DIR", str(base / "data"))
    os.environ.setdefault("JRC_DB_PATH", str(base / "data" / "jr_business.db"))
    os.environ.setdefault("JRC_EXPORT_DIR", str(base / "exports"))
    os.environ.setdefault("JRC_EVIDENCE_DIR", str(base / "evidence"))
    os.environ.setdefault("JRC_BACKUP_DIR", str(base / "backups"))
    os.environ.setdefault("JRC_LIVE_DIR", str(base))
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))


def _run_module(name: str, *, timeout: int = 180) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", name],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def _run_pytest(*, quick: bool, timeout: int = 300) -> tuple[int, str]:
    args = [sys.executable, "-m", "pytest", "tests", "-q", "--tb=line"]
    if quick:
        args = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_jrc_smoke.py",
            "tests/test_program_shell.py",
            "tests/test_server_control.py",
            "tests/test_messenger_permissions.py",
            "-q",
            "--tb=line",
        ]
    else:
        args.extend(["--ignore=tests/test_win11_ui_compat.py"])
    proc = subprocess.run(args, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def _record(report: SuiteReport, stage: str, name: str, code: int, out: str, *, warn_on_fail: bool = False) -> None:
    started = time.time()
    tail = "\n".join(out.splitlines()[-12:]).strip()
    if code == 0:
        status = "PASS"
    elif warn_on_fail:
        status = "WARN"
    else:
        status = "FAIL"
    report.results.append(
        CheckResult(
            name=name,
            stage=stage,
            status=status,
            seconds=round(time.time() - started, 2),
            detail=tail,
            exit_code=code,
        )
    )


def _run_check(report: SuiteReport, stage: str, name: str, module: str, *, warn_on_fail: bool = False, timeout: int = 180) -> None:
    t0 = time.time()
    try:
        code, out = _run_module(module, timeout=timeout)
    except subprocess.TimeoutExpired:
        report.results.append(
            CheckResult(name=name, stage=stage, status="FAIL", seconds=round(time.time() - t0, 2), detail="Timed out", exit_code=-1)
        )
        return
    tail = "\n".join(out.splitlines()[-12:]).strip()
    status = "PASS" if code == 0 else ("WARN" if warn_on_fail else "FAIL")
    report.results.append(
        CheckResult(name=name, stage=stage, status=status, seconds=round(time.time() - t0, 2), detail=tail, exit_code=code)
    )


def _check_folders(report: SuiteReport) -> None:
    t0 = time.time()
    required = ["data", "exports", "evidence", "backups", "logs", "chatgpt_imports", "business_standards"]
    missing = [d for d in required if not (BASE_DIR / d).exists()]
    for d in required:
        (BASE_DIR / d).mkdir(parents=True, exist_ok=True)
    if missing:
        report.results.append(
            CheckResult(
                name="Required folders",
                stage="1 — Environment",
                status="WARN",
                seconds=round(time.time() - t0, 2),
                detail=f"Created missing folders: {', '.join(missing)}",
            )
        )
    else:
        report.results.append(
            CheckResult(name="Required folders", stage="1 — Environment", status="PASS", seconds=round(time.time() - t0, 2))
        )


def _check_venv(report: SuiteReport) -> None:
    t0 = time.time()
    venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        report.results.append(
            CheckResult(name="Virtual environment", stage="1 — Environment", status="PASS", seconds=round(time.time() - t0, 2), detail=str(venv_py))
        )
    else:
        report.results.append(
            CheckResult(
                name="Virtual environment",
                stage="1 — Environment",
                status="WARN",
                seconds=round(time.time() - t0, 2),
                detail="No .venv found — run ensure_venv.bat or INSTALL_JR_JOB_MANAGER.bat",
            )
        )


def _check_version(report: SuiteReport) -> None:
    try:
        from app.program_manifest import APP_VERSION

        report.version = APP_VERSION
    except Exception:
        vf = BASE_DIR / "VERSION.txt"
        report.version = vf.read_text(encoding="utf-8").strip() if vf.is_file() else "unknown"


def _check_live_host(report: SuiteReport) -> None:
    t0 = time.time()
    try:
        import urllib.error
        import urllib.request

        port = int(os.environ.get("JRC_PORT", "8765"))
        url = f"http://127.0.0.1:{port}/api/health"
        with urllib.request.urlopen(url, timeout=3) as resp:
            ok = resp.status < 500
        status = "PASS" if ok else "FAIL"
        detail = f"{url} responded OK"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        status = "WARN"
        detail = f"Host not running on port {os.environ.get('JRC_PORT', '8765')}: {exc}. Start host from Start Center if you need LAN/mobile access."
    report.results.append(
        CheckResult(name="Live host health probe", stage="8 — Live host", status=status, seconds=round(time.time() - t0, 2), detail=detail)
    )


def run_suite(
    *,
    mode: str = "standard",
    with_host: bool = False,
    strict: bool = False,
) -> SuiteReport:
    _setup_env(BASE_DIR)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    report = SuiteReport(
        mode=mode,
        started=time.strftime("%Y-%m-%d %H:%M:%S"),
        finished="",
        base_dir=str(BASE_DIR),
        python=sys.executable,
    )
    _check_version(report)

    # Stage 1 — Environment
    _check_folders(report)
    _check_venv(report)

    # Stage 2 — Automated tests
    t0 = time.time()
    try:
        code, out = _run_pytest(quick=(mode == "quick"))
        status = "PASS" if code == 0 else "FAIL"
        report.results.append(
            CheckResult(
                name="Automated tests (pytest)",
                stage="2 — Automated tests",
                status=status,
                seconds=round(time.time() - t0, 2),
                detail="\n".join(out.splitlines()[-8:]).strip(),
                exit_code=code,
            )
        )
    except subprocess.TimeoutExpired:
        report.results.append(
            CheckResult(name="Automated tests (pytest)", stage="2 — Automated tests", status="FAIL", seconds=300, detail="Timed out", exit_code=-1)
        )

    # Stage 3 — Database & core health
    _run_check(report, "3 — Database & core", "System check + schema repair", "app.system_check")

    # Stage 4 — Core verification
    core_checks = [
        ("Final program verify", "app.final_program_verify"),
        ("Login / install check", "app.login_install_system_check"),
        ("UI dashboard check", "app.ui_dashboard_final_check"),
    ]
    if mode != "quick":
        core_checks.extend([
            ("Customer portal check", "app.customer_request_final_check"),
            ("Permission view check", "app.permission_view_check"),
            ("Dashboard role check", "app.dashboard_role_check"),
        ])
    for label, mod in core_checks:
        _run_check(report, "4 — Core verification", label, mod)

    # Stage 5 — Security
    if mode != "quick":
        security_checks = [
            ("Admin security check", "app.admin_security_final_check"),
            ("Security perspective audit", "app.security_perspective_audit"),
            ("Account request verification", "app.account_request_verification_check"),
            ("File access security", "app.file_access_security"),
            ("Device shutdown check", "app.device_shutdown_final_check"),
        ]
        for label, mod in security_checks:
            _run_check(report, "5 — Security", label, mod)

    # Stage 6 — Office AI & v8
    if mode != "quick":
        _run_check(report, "6 — Office AI & v8", "Office AI verification", "app.office_ai_verification_check")
        if mode == "full":
            _run_check(report, "6 — Office AI & v8", "v8 full build verify", "app.v8_build_verify", timeout=600)

    # Stage 7 — Cloud & integration (warn if local-only)
    if mode in ("standard", "full"):
        integration_checks = [
            ("Cloud deploy check", "app.cloud_deploy_check"),
            ("Internet / cloud security verify", "app.internet_cloud_security_verify"),
            ("Business sources security audit", "app.business_sources_security_audit"),
            ("Live release verify", "app.live_release_verify"),
        ]
        for label, mod in integration_checks:
            warn = mod in ("app.business_sources_security_audit", "app.live_release_verify", "app.cloud_deploy_check")
            _run_check(report, "7 — Cloud & integration", label, mod, warn_on_fail=warn)

    # Stage 8 — Full phase verification
    if mode == "full":
        t0 = time.time()
        try:
            from app.run_phase_verification import run_phase_verification

            code, path = run_phase_verification(BASE_DIR)
            status = "PASS" if code == 0 else "WARN"
            report.results.append(
                CheckResult(
                    name="Phase verification (all phases)",
                    stage="8 — Full phase verify",
                    status=status,
                    seconds=round(time.time() - t0, 2),
                    detail=f"Report: {path.name}",
                    exit_code=code,
                )
            )
        except Exception as exc:
            report.results.append(
                CheckResult(
                    name="Phase verification (all phases)",
                    stage="8 — Full phase verify",
                    status="FAIL",
                    seconds=round(time.time() - t0, 2),
                    detail=str(exc),
                )
            )

    # Stage 9 — Live host (optional)
    if with_host or mode == "full":
        _check_live_host(report)

    report.finished = time.strftime("%Y-%m-%d %H:%M:%S")
    return report


def _format_report(report: SuiteReport) -> str:
    lines = [
        "J & R CONSTRUCTION MANAGER — FULL SYSTEM TEST SUITE",
        "=" * 62,
        f"Mode:     {report.mode}",
        f"Version:  {report.version}",
        f"Started:  {report.started}",
        f"Finished: {report.finished}",
        f"Install:  {report.base_dir}",
        f"Python:   {report.python}",
        "",
        "SUMMARY",
        f"  PASS: {report.passed}  FAIL: {report.failed}  WARN: {report.warned}  SKIP: {report.skipped}",
        "",
    ]

    current_stage = ""
    for r in report.results:
        if r.stage != current_stage:
            current_stage = r.stage
            lines.append(current_stage)
            lines.append("-" * 40)
        icon = {"PASS": "[OK]", "FAIL": "[FAIL]", "WARN": "[WARN]", "SKIP": "[SKIP]"}.get(r.status, "[?]")
        lines.append(f"  {icon} {r.name} ({r.seconds}s)")
        if r.detail and r.status != "PASS":
            for ln in r.detail.splitlines()[:6]:
                lines.append(f"       {ln}")
    lines.append("")
    if report.failed:
        lines.append("OVERALL: NEEDS ATTENTION — fix FAIL items before sharing access or going live.")
        lines.append("See docs/SYSTEM_TEST_SUITE_GUIDE.md for what each check means and how to fix failures.")
    elif report.warned:
        lines.append("OVERALL: PASSED WITH WARNINGS — core system OK; review WARN items (often Dropbox/cloud setup).")
    else:
        lines.append("OVERALL: PASS — system checks look good for this install.")
    return "\n".join(lines)


def _write_reports(report: SuiteReport, text: str) -> tuple[Path, Path]:
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = EXPORT_DIR / f"JRC_Full_System_Test_Suite_{ts}.txt"
    latest = BASE_DIR / "SYSTEM_TEST_SUITE_LAST_REPORT.txt"
    json_out = EXPORT_DIR / f"JRC_Full_System_Test_Suite_{ts}.json"
    out.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    json_out.write_text(json.dumps({**asdict(report)}, indent=2), encoding="utf-8")
    return out, latest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="J & R Construction Manager full system test suite")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true", help="Fast daily check (~2-3 min)")
    mode.add_argument("--standard", action="store_true", help="Recommended weekly check (~5-8 min)")
    mode.add_argument("--full", action="store_true", help="Complete verification (~10-15 min)")
    parser.add_argument("--with-host", action="store_true", help="Probe live host on port 8765")
    parser.add_argument("--strict", action="store_true", help="Treat WARN as FAIL for exit code")
    args = parser.parse_args(argv)

    run_mode = "standard"
    if args.quick:
        run_mode = "quick"
    elif args.full:
        run_mode = "full"

    report = run_suite(mode=run_mode, with_host=args.with_host, strict=args.strict)
    text = _format_report(report)
    out, latest = _write_reports(report, text)
    print(text)
    print(f"\nReport saved: {out}")
    print(f"Latest copy:  {latest}")

    if report.failed:
        return 1
    if args.strict and report.warned:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
