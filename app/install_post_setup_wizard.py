"""
Post-install setup wizard — foolproof next steps for owner and customer guidance.
"""
from __future__ import annotations

try:
    from app.win11_compat import enable_win_dpi_awareness
    enable_win_dpi_awareness()
except Exception:
    pass

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None

BASE_DIR = Path(__file__).resolve().parents[1]
PY = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
if not PY.exists():
    PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PY_CMD = str(PY if PY.exists() else sys.executable)


def _launch(module: str, log_name: str) -> None:
    from app.install_setup_log import log_event

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log = log_dir / log_name
    startupinfo = None
    flags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with log.open("a", encoding="utf-8", errors="replace") as f:
        f.write("\n--- Post-setup wizard launch ---\n")
        subprocess.Popen(
            [PY_CMD, "-m", module],
            cwd=str(BASE_DIR),
            stdout=f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=flags,
        )
    log_event(BASE_DIR, "PostSetup", f"Launched {module}")


def run_wizard(profile: str = "OwnerMaster") -> int:
    if tk is None:
        return 2
    from app.install_setup_log import log_event, mark_step, write_setup_report

    root = tk.Tk()
    root.title("J & R Construction Manager — Setup Complete")
    root.geometry("640x520")
    root.configure(bg="#0a0a0a")
    root.resizable(False, False)

    title = tk.Label(root, text="Setup wizard", bg="#0a0a0a", fg="#a3e635", font=("Segoe UI", 18, "bold"))
    title.pack(anchor="w", padx=24, pady=(20, 8))
    body = tk.Label(
        root,
        text="",
        bg="#0a0a0a",
        fg="#d4d4d4",
        font=("Segoe UI", 11),
        wraplength=580,
        justify="left",
    )
    body.pack(anchor="w", padx=24, pady=(0, 16))

    steps_owner = [
        (
            "Step 1 — Secure login",
            "Secure Local Login should be open. Sign in with your owner account.\n"
            "If this is first setup on this PC, default is ivygrows / ivygrows — change password immediately after login.",
        ),
        (
            "Step 2 — Open Start Center",
            "Start Center is your daily launcher: Office, admin tools, and mobile hosting.",
        ),
        (
            "Step 3 — Run your business",
            "Open Office for jobs, invoices, payroll, and files.\n"
            "Use Admin & security → Start Local Host → Admin Web Panel for users and active sessions.",
        ),
        (
            "Step 4 — Customers & remote users",
            "Customers do NOT install this program.\n"
            "Share your web link for /register (account request) or /mobile after you start the local host or cloud server.",
        ),
        (
            "All set",
            "Setup report saved to INSTALL_SETUP_REPORT.txt in your install folder.\n"
            "Logs: logs/install_setup_journal.log",
        ),
    ]
    steps_worker = [
        (
            "Worker / remote client",
            "This PC has the app shell only — no business database is stored here.\n"
            "Ask Jacob for the company cloud/host URL and sign in through the browser.",
        ),
        (
            "Open Start Center",
            "Use Mobile Links or Cloud Access from Start Center to connect.",
        ),
        (
            "Done",
            "Setup report saved. Contact admin if login links do not work.",
        ),
    ]
    steps = steps_owner if profile == "OwnerMaster" else steps_worker
    idx = {"i": 0}

    btns = tk.Frame(root, bg="#0a0a0a")
    btns.pack(fill="x", padx=24, pady=12)

    def show_step():
        s = steps[idx["i"]]
        title.configure(text=s[0])
        body.configure(text=s[1])

    def next_step():
        i = idx["i"]
        if i == 1 and profile == "OwnerMaster":
            _launch("app.start_center", "start_center_post_setup.log")
        if i == 0 and profile == "OwnerMaster":
            _launch("app.local_login_gate", "local_login_gate_post_setup.log")
        if i >= len(steps) - 1:
            mark_step(BASE_DIR, "setup_complete", "ok", "Post-install wizard finished")
            write_setup_report(BASE_DIR)
            log_event(BASE_DIR, "PostSetup", "Wizard completed")
            messagebox.showinfo("Setup complete", "You're ready to use J & R Construction Manager.\n\nSee INSTALL_SETUP_REPORT.txt for a written summary.", parent=root)
            root.destroy()
            return
        idx["i"] += 1
        show_step()

    def open_report():
        from app.install_setup_log import write_setup_report

        path = write_setup_report(BASE_DIR)
        try:
            import os

            os.startfile(str(path))
        except Exception:
            messagebox.showinfo("Report", f"Report saved:\n{path}", parent=root)

    tk.Button(btns, text="Next →", command=next_step, bg="#84cc16", fg="#000", relief="flat", padx=16, pady=10).pack(
        side="left", padx=(0, 8)
    )
    tk.Button(btns, text="Open Setup Report", command=open_report, bg="#374151", fg="#fff", relief="flat", padx=12, pady=10).pack(
        side="left", padx=(0, 8)
    )
    tk.Button(btns, text="Close", command=root.destroy, bg="#1f2937", fg="#fff", relief="flat", padx=12, pady=10).pack(
        side="right"
    )
    mark_step(BASE_DIR, "post_login", "started", "Post-install wizard opened")
    log_event(BASE_DIR, "PostSetup", f"Wizard opened profile={profile}")
    show_step()
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", default=str(BASE_DIR))
    parser.add_argument("--profile", default="OwnerMaster", choices=["OwnerMaster", "WorkerClient"])
    args = parser.parse_args(argv)
    install_dir = Path(args.install_dir).resolve()
    return run_wizard_for(install_dir, args.profile)


def run_wizard_for(install_dir: Path, profile: str) -> int:
    global BASE_DIR, PY_CMD
    BASE_DIR = install_dir
    py = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
    PY_CMD = str(py if py.exists() else BASE_DIR / ".venv" / "Scripts" / "python.exe")
    return run_wizard(profile)


if __name__ == "__main__":
    raise SystemExit(main())
