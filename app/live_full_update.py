"""
Full live update — sync files, verify packages, run checks, log and save report.
Run from repo (syncs to live) or from installed folder (verify in place).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

SYNC_GLOBS = (
    ("app", "*.py"),
)
SYNC_FILES = (
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
    "RUN_SYSTEM_TEST_SUITE.bat",
    "LIVE_FULL_UPDATE.vbs",
    "LIVE_UPDATE_REPORT.txt",
)


def live_install_dirs() -> List[Path]:
    paths = []
    env = os.environ.get("JRC_LIVE_DIR", "").strip()
    if env:
        paths.append(Path(env))
    local = Path(os.path.expandvars(r"%LOCALAPPDATA%\J_and_R_Construction_Manager"))
    if local not in paths:
        paths.append(local)
    for desk in (
        Path.home() / "Desktop" / "J and R Construction Manager",
        Path.home() / "OneDrive" / "Desktop" / "J and R Construction Manager",
        Path.home() / "Documents" / "JRC" / "J-and-R-construction-management",
    ):
        if desk not in paths:
            paths.append(desk)
    return [p for p in paths if p.exists()]


def sync_tree(src: Path, dst: Path) -> List[str]:
    src = src.resolve()
    dst = dst.resolve()
    notes: List[str] = []
    if not dst.exists():
        dst.mkdir(parents=True, exist_ok=True)
        notes.append(f"Created {dst}")
    app_src = src / "app"
    app_dst = dst / "app"
    if app_src.exists():
        app_dst.mkdir(parents=True, exist_ok=True)
        for py in app_src.glob("*.py"):
            shutil.copy2(py, app_dst / py.name)
        for sub in app_src.iterdir():
            if sub.is_dir() and sub.name not in ("__pycache__",):
                shutil.copytree(sub, app_dst / sub.name, dirs_exist_ok=True)
                notes.append(f"Synced app/{sub.name}/")
        notes.append(f"Synced {len(list(app_src.glob('*.py')))} app modules")
    scripts_src = src / "scripts"
    scripts_dst = dst / "scripts"
    if scripts_src.exists():
        scripts_dst.mkdir(parents=True, exist_ok=True)
        for item in scripts_src.iterdir():
            if item.is_file():
                shutil.copy2(item, scripts_dst / item.name)
        notes.append("Synced scripts/")
    for rel in SYNC_FILES:
        s = src / rel
        if s.exists():
            d = dst / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            notes.append(f"Copied {rel}")
    assets = src / "assets"
    if assets.exists():
        ad = dst / "assets"
        ad.mkdir(parents=True, exist_ok=True)
        for item in assets.iterdir():
            if item.is_file():
                shutil.copy2(item, ad / item.name)
        notes.append("Synced assets/")
    return notes


def ensure_data_dirs(base: Path) -> None:
    from app.program_manifest import REQUIRED_DIRS

    for d in REQUIRED_DIRS:
        (base / d).mkdir(parents=True, exist_ok=True)


def run_live_update(source_dir: Path | None = None, sync: bool = True) -> Tuple[int, Path]:
    from app.admin_developer_suite import (
        build_developer_status,
        is_admin_developer_pc,
        run_verify_bundle,
        write_developer_report,
    )
    from app.emergency_access import ensure_mastery_key_on_owner_install
    from app.install_setup_log import log_event, mark_step, write_setup_report
    from app.program_manifest import APP_VERSION, package_status, verify_layout

    src = Path(source_dir or BASE_DIR).resolve()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "J and R Construction Manager — FULL LIVE UPDATE REPORT",
        "=" * 62,
        f"Generated: {ts}",
        f"Version: {APP_VERSION}",
        f"Source: {src}",
        "",
    ]
    errors = 0

    targets = live_install_dirs() if sync else [src]
    if sync and src not in targets:
        for t in list(targets):
            if t.resolve() == src:
                targets.remove(t)
        if not any(t.resolve() == src for t in targets):
            pass
    if sync:
        lines.append("SYNC TARGETS")
        for target in targets:
            if not target.exists():
                lines.append(f"  [SKIP] missing {target}")
                continue
            if target.resolve() == src.resolve():
                ensure_data_dirs(target)
                seeded, seed_msg = ensure_mastery_key_on_owner_install(target)
                lines.append(f"  [OK] {target} (in-place verify)")
                lines.append(f"       Emergency: {seed_msg}")
            else:
                notes = sync_tree(src, target)
                ensure_data_dirs(target)
                seeded, seed_msg = ensure_mastery_key_on_owner_install(target)
                lines.append(f"  [OK] {target}")
                for n in notes:
                    lines.append(f"       {n}")
                lines.append(f"       Emergency: {seed_msg}")
            log_event(target, "LiveUpdate", f"Synced from {src}", level="INFO", step="setup_complete")
            mark_step(target, "setup_complete", "ok", f"Live update {APP_VERSION}")
            write_setup_report(target)
        lines.append("")

    # Office sync + phase hooks on each synced target
    if sync:
        lines.append("OFFICE SYNC (all targets)")
        for target in targets:
            if not target.exists():
                continue
            try:
                os.environ["JRC_DATA_DIR"] = str(target / "data")
                os.environ["JRC_DB_PATH"] = str(target / "data" / "jr_business.db")
                from app.office_records_sync import run_office_sync

                rep = run_office_sync(target)
                lines.append(f"  {target.name}: inserted={rep.get('jobs_inserted',0)} updated={rep.get('jobs_updated',0)}")
                if rep.get("errors"):
                    errors += len(rep["errors"])
                    for e in rep["errors"]:
                        lines.append(f"    ERROR: {e}")
            except Exception as exc:
                lines.append(f"  {target}: office sync failed: {exc}")
                errors += 1
        lines.append("")

    verify_base = targets[0] if targets else src
    os.environ.setdefault("JRC_DATA_DIR", str(verify_base / "data"))
    os.environ.setdefault("JRC_LIVE_DIR", str(verify_base))

    ok_files, missing, warnings = verify_layout(verify_base)
    lines.append("FILE MANIFEST")
    lines.append(f"  OK: {len(ok_files)} paths")
    if missing:
        errors += len(missing)
        lines.append(f"  MISSING ({len(missing)}):")
        for m in missing:
            lines.append(f"    - {m}")
    if warnings:
        lines.append(f"  WARNINGS ({len(warnings)}):")
        for w in warnings:
            lines.append(f"    - {w}")
    lines.append("")

    pkgs = package_status()
    lines.append("PYTHON PACKAGES")
    for name, ok in pkgs.items():
        if not ok:
            errors += 1
        lines.append(f"  [{'OK' if ok else 'MISSING'}] {name}")
    lines.append("")

    status = build_developer_status(verify_base)
    lines.append(f"Admin developer PC: {status['admin_pc']}")
    lines.append(f"Installer source: {status.get('installer_source') or '(not recorded)'}")
    lines.append("")

    bundle_errors, bundle_report = run_verify_bundle(verify_base)
    errors += bundle_errors
    lines.append(f"VERIFY BUNDLE: {bundle_report.name} ({bundle_errors} failures)")
    lines.append("")

    dev_report = write_developer_report(verify_base)
    lines.append(f"Developer status: {dev_report.name}")
    lines.append("")

    # Share links + cloud_connect.json + Dropbox guest-link docs (office / host profile)
    lines.append("SHARE LINKS SYNC")
    try:
        from app.share_links_sync import run_share_links_sync

        sl = run_share_links_sync(probe=True, write_dropbox=True)
        lines.append(f"  connect: {sl.get('urls', {}).get('connect_url', '')}")
        lines.append(f"  version: {sl.get('version', APP_VERSION)} git: {sl.get('git_head', '') or 'n/a'}")
        h = sl.get("health") or {}
        lines.append(f"  host health: {'OK' if h.get('ok') else h.get('error', 'fail')}")
        for note in sl.get("dropbox_written") or []:
            lines.append(f"  {note}")
        if not sl.get("ok"):
            errors += 1
            lines.append("  ERROR: share link sync incomplete")
    except Exception as exc:
        lines.append(f"  share_links_sync failed: {exc}")
        errors += 1
    lines.append("")

    lines.append(f"SUMMARY: {errors} issue(s)")
    if errors == 0:
        lines.append("Overall: LIVE UPDATE OK — files, packages, and verification checks passed.")
    else:
        lines.append("Overall: NEEDS ATTENTION — review missing items and verify logs in exports/ and logs/.")

    report_path = verify_base / "LIVE_UPDATE_REPORT.txt"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    export_copy = verify_base / "exports" / f"JRC_Live_Full_Update_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    export_copy.parent.mkdir(parents=True, exist_ok=True)
    export_copy.write_text("\n".join(lines), encoding="utf-8")

    try:
        log_event(
            verify_base,
            "LiveFullUpdate",
            f"Live update {APP_VERSION}: {errors} issues — report {report_path.name}",
            level="INFO" if errors == 0 else "ERROR",
            step="setup_complete",
            extra={"errors": errors, "report": str(report_path), "version": APP_VERSION},
        )
        write_setup_report(verify_base)
    except Exception:
        pass

    print("\n".join(lines))
    print(f"\nReport saved: {report_path}")
    print(f"Export copy: {export_copy}")
    return 1 if errors else 0, report_path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    no_sync = "--no-sync" in args
    src = BASE_DIR
    for a in args:
        if a.startswith("--source="):
            src = Path(a.split("=", 1)[1])
    code, _ = run_live_update(src, sync=not no_sync)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
