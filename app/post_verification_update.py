"""Install/update pipeline — runs automatically after account verification."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple

DEBOUNCE_HOURS = 6
MARKER_NAME = ".last_post_verification_update.json"


def _is_worker_client(base: Path) -> bool:
    profile = base / "data" / "install_profile.json"
    if not profile.is_file():
        return False
    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
        return str(data.get("profile", "")).strip() == "WorkerClient"
    except Exception:
        return False


def _allowed_user(user: dict | None) -> bool:
    if not user:
        return False
    role = str(user.get("role") or "").lower()
    return role in {"admin", "manager", "owner"}


def should_run_post_verification_update(
    install_dir: Path,
    user: dict | None = None,
    *,
    force: bool = False,
) -> Tuple[bool, str]:
    base = Path(install_dir).resolve()
    if _is_worker_client(base):
        return False, "Worker client — no local install/update"

    try:
        from app.startup_setup import evaluate_setup_state

        action, detail = evaluate_setup_state(base)
        if action == "need_installer":
            return False, f"Install incomplete — use Install/Update wizard first ({detail})"
        if action == "need_venv":
            return False, "Python environment not ready"
    except Exception as exc:
        return False, f"Setup state check failed: {exc}"

    try:
        from app.admin_developer_suite import is_admin_developer_pc

        admin_pc = is_admin_developer_pc(base)
    except Exception:
        admin_pc = False

    if not admin_pc and not _allowed_user(user):
        return False, "Post-verification update is for admin PCs or admin/manager accounts"

    if force or os.environ.get("JRC_FORCE_POST_VERIFY_UPDATE", "").strip() == "1":
        return True, "Forced post-verification update"

    marker = base / "data" / MARKER_NAME
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            last = float(data.get("ts", 0))
            if time.time() - last < DEBOUNCE_HOURS * 3600:
                return False, f"Update ran recently ({data.get('when', 'unknown')})"
        except Exception:
            pass

    from app.install_live_sync import resolve_master

    master = resolve_master()
    if master and master.resolve() != base.resolve():
        return True, f"Sync from master install: {master}"
    if admin_pc:
        return True, "Admin developer PC — verify and sync live installs"
    return True, "Post-verification update scheduled"


def _write_marker(base: Path, detail: str, exit_code: int) -> None:
    marker = base / "data" / MARKER_NAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "ts": time.time(),
                "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                "detail": detail,
                "exit_code": exit_code,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _python_cmd(base: Path) -> Path:
    for rel in (".venv/Scripts/python.exe", ".venv/Scripts/pythonw.exe"):
        p = base / rel
        if p.is_file():
            return p
    return Path(sys.executable)


def run_post_verification_update_pipeline(
    install_dir: Path,
    *,
    source_dir: Path | None = None,
    user: dict | None = None,
) -> Tuple[int, str]:
    """Run light sync + full live update + phase verification (foreground)."""
    base = Path(install_dir).resolve()
    ok, reason = should_run_post_verification_update(base, user, force=False)
    if not ok:
        return 0, reason

    lines = [f"Post-verification update: {reason}", f"Install dir: {base}"]

    try:
        from app.install_live_sync import resolve_master, sync_from_master_if_available

        sync_notes = sync_from_master_if_available(base)
        if sync_notes.get("synced"):
            lines.append(f"Pre-sync: {sync_notes.get('notes', [])}")
        master = resolve_master()
        src = Path(source_dir or master or base).resolve()
    except Exception as exc:
        src = Path(source_dir or base).resolve()
        lines.append(f"Pre-sync skipped: {exc}")

    exit_code = 0
    try:
        from app.live_full_update import run_live_update

        code, report = run_live_update(src, sync=True)
        lines.append(f"Live update exit {code} — report {report.name}")
        exit_code = max(exit_code, code)
    except Exception as exc:
        lines.append(f"Live update failed: {exc}")
        exit_code = 1

    try:
        py = _python_cmd(base)
        proc = subprocess.run(
            [str(py), "-m", "app.run_phase_verification", str(base)],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        lines.append(f"Phase verification exit {proc.returncode}")
        exit_code = max(exit_code, proc.returncode or 0)
    except Exception as exc:
        lines.append(f"Phase verification failed: {exc}")
        exit_code = max(exit_code, 1)

    try:
        from app.install_setup_log import log_event, mark_step, write_setup_report

        log_event(
            base,
            "PostVerificationUpdate",
            "\n".join(lines),
            level="INFO" if exit_code == 0 else "ERROR",
            step="setup_complete",
        )
        mark_step(base, "setup_complete", "ok" if exit_code == 0 else "warn", reason)
        write_setup_report(base)
    except Exception:
        pass

    _write_marker(base, reason, exit_code)
    log_path = base / "logs" / "post_verification_update_last.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return exit_code, "\n".join(lines)


def spawn_post_verification_update(
    install_dir: Path,
    user: dict | None = None,
) -> Tuple[bool, str]:
    """Background post-verification update (non-blocking)."""
    base = Path(install_dir).resolve()
    ok, reason = should_run_post_verification_update(base, user, force=False)
    if not ok:
        return False, reason

    py = _python_cmd(base)
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "post_verification_update_last.log"
    startupinfo = None
    flags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = [str(py), "-m", "app.post_verification_update", "--run", f"--install-dir={base}"]
    try:
        with log_path.open("a", encoding="utf-8", errors="replace") as logf:
            logf.write(f"\n--- spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{reason}\n")
            subprocess.Popen(
                cmd,
                cwd=str(base),
                stdout=logf,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=flags,
            )
        return True, f"Install/update running in background after sign-in ({reason})"
    except Exception as exc:
        return False, f"Could not start post-verification update: {exc}"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--run" not in args:
        print("Usage: python -m app.post_verification_update --run --install-dir=PATH")
        return 2
    install_dir = Path(__file__).resolve().parents[1]
    source_dir = None
    for arg in args:
        if arg.startswith("--install-dir="):
            install_dir = Path(arg.split("=", 1)[1])
        elif arg.startswith("--source="):
            source_dir = Path(arg.split("=", 1)[1])
    code, msg = run_post_verification_update_pipeline(install_dir, source_dir=source_dir)
    print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
