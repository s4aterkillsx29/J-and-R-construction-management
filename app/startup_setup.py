"""Detect incomplete install/setup and launch the correct wizard (no visible CMD)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

BASE_DIR = Path(__file__).resolve().parents[1]


def _hidden_popen(args: list[str], cwd: Path) -> subprocess.Popen | None:
    log_dir = cwd / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / "startup_setup_last.log"
    startupinfo = None
    flags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with log.open("a", encoding="utf-8", errors="replace") as f:
            f.write(f"\n--- startup launch: {' '.join(args)} ---\n")
            return subprocess.Popen(
                args,
                cwd=str(cwd),
                stdout=f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=flags,
            )
    except Exception:
        return None


def evaluate_setup_state(base_dir: Path | None = None) -> Tuple[str, str]:
    """
    Returns (action, detail):
      ok — nothing to do
      need_installer — run full Install/Update wizard
      need_first_run — run Secure Login + post-setup wizard
      need_venv — run hidden ensure_venv only
    """
    base = Path(base_dir or BASE_DIR).resolve()
    pyw = base / ".venv" / "Scripts" / "pythonw.exe"
    if not pyw.exists():
        ensure_marker = base / "data" / ".venv_ready"
        if not ensure_marker.exists():
            return "need_venv", "Python environment missing"
        return "need_installer", "Virtual environment not ready — run Install/Update"

    profile = base / "data" / "install_profile.json"
    state_path = base / "data" / "install_setup_state.json"
    db_path = base / "data" / "jr_business.db"
    if not profile.exists() and not state_path.exists():
        if db_path.exists():
            return "need_first_run", "Existing database found — opening login and setup wizard"
        return "need_installer", "First-time install not completed"

    steps: dict = {}
    if state_path.exists():
        try:
            steps = json.loads(state_path.read_text(encoding="utf-8")).get("steps", {})
        except Exception:
            return "need_installer", "Install state unreadable"

    install_status = (steps.get("install_files") or {}).get("status", "")
    if install_status not in ("ok", "warn"):
        if not profile.exists():
            return "need_installer", "Program files not installed"

    complete = (steps.get("setup_complete") or {}).get("status", "")
    post_login = (steps.get("post_login") or {}).get("status", "")
    if complete == "ok":
        return "ok", "Setup complete"
    if post_login in ("ok", "started") and install_status == "ok":
        return "ok", "Post-install in progress or done"
    if install_status == "ok":
        return "need_first_run", "Install finished — login and setup wizard still needed"
    return "need_installer", "Install/update wizard required"


def launch_ensure_venv_hidden(base_dir: Path) -> None:
    bat = base / "ensure_venv.bat"
    if not bat.exists():
        return
    if os.name != "nt":
        return
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            ["cmd.exe", "/c", str(bat)],
            cwd=str(base_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=flags,
            check=False,
        )
        marker = base_dir / "data" / ".venv_ready"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="ascii")
    except Exception:
        pass


def launch_installer(base_dir: Path) -> bool:
    base = Path(base_dir).resolve()
    for rel in ("!!! START INSTALL HERE.vbs", "INSTALL_J_AND_R_MANAGER.vbs"):
        vbs = base / rel
        if vbs.exists():
            os.startfile(str(vbs))
            return True
    ps1 = base / "install_jr_job_manager_ui.ps1"
    if ps1.exists() and os.name == "nt":
        _hidden_popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Normal",
                "-File",
                str(ps1),
            ],
            base,
        )
        return True
    return False


def launch_first_run_setup(base_dir: Path, *, auto: bool = True) -> bool:
    base = Path(base_dir).resolve()
    pyw = base / ".venv" / "Scripts" / "pythonw.exe"
    py = base / ".venv" / "Scripts" / "python.exe"
    cmd = str(pyw if pyw.exists() else py if py.exists() else sys.executable)
    args = [cmd, "-m", "app.first_run_login_setup"]
    if auto:
        args.append("--auto")
    proc = _hidden_popen(args, base)
    return proc is not None


def maybe_run_startup_setup(base_dir: Path | None = None) -> Tuple[str, str]:
    """Run the appropriate setup action once at program start. Returns (action, detail)."""
    base = Path(base_dir or BASE_DIR).resolve()
    action, detail = evaluate_setup_state(base)
    if action == "need_venv":
        launch_ensure_venv_hidden(base)
        action, detail = evaluate_setup_state(base)
    if action == "need_installer":
        launch_installer(base)
    elif action == "need_first_run":
        launch_first_run_setup(base, auto=True)
    return action, detail
