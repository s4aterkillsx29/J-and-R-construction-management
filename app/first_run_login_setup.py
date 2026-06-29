"""
JRC First Setup / Login Bridge — opens Secure Local Login + post-install wizard.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
LOG_DIR = BASE_DIR / "logs"
for d in (BASE_DIR / "data", LOG_DIR, BASE_DIR / "exports"):
    d.mkdir(exist_ok=True)

PYTHONW = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PY_CMD = str(PYTHONW if PYTHONW.exists() else PYTHON if PYTHON.exists() else sys.executable)


def launch_module(module: str, log_name: str):
    log = LOG_DIR / log_name
    startupinfo = None
    flags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with log.open("a", encoding="utf-8", errors="replace") as f:
        f.write("\n--- First Setup Launch ---\n")
        try:
            return subprocess.Popen(
                [PY_CMD, "-m", module],
                cwd=str(BASE_DIR),
                stdout=f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=flags,
            ), log
        except Exception as e:
            f.write("LAUNCH ERROR: " + str(e) + "\n")
            return None, log


def main() -> int:
    auto = "--auto" in sys.argv
    try:
        from app.install_setup_log import log_event, write_setup_report

        log_event(BASE_DIR, "FirstSetup", "First setup / login bridge opened")
    except Exception:
        pass

    if tk is None or auto:
        proc, log = launch_module("app.local_login_gate", "local_login_gate_from_setup.log")
        if proc is None:
            return 1
        launch_module("app.install_post_setup_wizard", "post_setup_from_first_run.log")
        try:
            from app.install_setup_log import write_setup_report

            write_setup_report(BASE_DIR)
        except Exception:
            pass
        return 0

    root = tk.Tk()
    root.withdraw()
    msg = (
        "J & R Construction Manager — foolproof setup order:\n\n"
        "1) Secure Local Login opens now (sign in on THIS PC only)\n"
        "2) Setup wizard shows next steps\n"
        "3) Start Center → Open Office for daily business\n\n"
        "Customers / remote users: do NOT use this tool.\n"
        "They use Jacob's browser link only (/register or /mobile).\n\n"
        "Open setup now?"
    )
    if not messagebox.askyesno("JRC First Setup / Login", msg):
        return 0

    proc, log = launch_module("app.local_login_gate", "local_login_gate_from_setup.log")
    if proc is None:
        messagebox.showwarning("Could not open local login", f"Local Login Gate could not open.\n\nLog: {log}")
        return 1

    launch_module("app.install_post_setup_wizard", "post_setup_from_first_run.log")
    try:
        from app.install_setup_log import write_setup_report

        write_setup_report(BASE_DIR)
    except Exception:
        pass

    messagebox.showinfo(
        "Setup Started",
        "Secure Local Login and the setup wizard are opening.\n\n"
        "Log file: logs/install_setup_journal.log\n"
        "Summary: INSTALL_SETUP_REPORT.txt",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
