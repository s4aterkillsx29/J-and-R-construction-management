"""Program startup: login → update splash → main Start Center."""
from __future__ import annotations

import os
import sys
import threading
import time

try:
    from app.win11_compat import enable_win_dpi_awareness, bootstrap_tk_window
    enable_win_dpi_awareness()
except Exception:
    pass

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

BASE_DIR = Path(__file__).resolve().parents[1]


def _theme():
    try:
        from app import ui_theme as theme

        return theme.BG, theme.PANEL, theme.TEXT, theme.MUTED, theme.ACCENT, theme.INFO
    except Exception:
        return "#0a0f1c", "#111827", "#f5f5f5", "#a3a3a3", "#84cc16", "#a3e635"


class StartupSplash:
    """Loading UI while post-verification update runs."""

    def __init__(self, username: str = ""):
        self.bg, self.panel, self.text, self.muted, self.accent, self.info = _theme()
        self.root = tk.Tk()
        try:
            bootstrap_tk_window(self.root)
        except Exception:
            pass
        self.root.title("J & R Construction Manager — Starting")
        self.root.geometry("520x220")
        self.root.configure(bg=self.bg)
        self.root.resizable(False, False)
        try:
            from app import ui_theme as theme

            theme.apply_window_icon(self.root, BASE_DIR / "assets" / "j_and_r_manager_icon.ico")
        except Exception:
            pass
        tk.Label(
            self.root,
            text="J & R Construction Manager",
            bg=self.bg,
            fg=self.text,
            font=("Segoe UI", 16, "bold"),
        ).pack(pady=(18, 4))
        who = f"Signed in as {username}" if username else "Account verified"
        tk.Label(self.root, text=who, bg=self.bg, fg=self.muted, font=("Segoe UI", 10)).pack()
        self.status = tk.StringVar(value="Preparing install/update sync...")
        tk.Label(self.root, textvariable=self.status, bg=self.bg, fg=self.info, font=("Segoe UI", 10), wraplength=480).pack(pady=(12, 8))
        self.bar = ttk.Progressbar(self.root, mode="indeterminate", length=460)
        self.bar.pack(pady=8)
        self.version = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.version, bg=self.bg, fg=self.muted, font=("Segoe UI", 9)).pack(pady=(4, 0))
        self.bar.start(12)
        self._done = False
        self._error = ""

    def set_status(self, msg: str) -> None:
        self.status.set(msg)
        self.root.update_idletasks()

    def set_version(self, ver: str) -> None:
        self.version.set(ver)

    def close(self) -> None:
        if self._done:
            return
        self._done = True
        try:
            self.bar.stop()
            self.root.destroy()
        except Exception:
            pass

    def show_error(self, msg: str) -> None:
        self._error = msg
        messagebox.showwarning("Startup Update", msg, parent=self.root)


def _ensure_login() -> dict | None:
    from app.desktop_session import create_desktop_session, get_active_desktop_session, register_program_exit_handler

    register_program_exit_handler(BASE_DIR)
    existing = get_active_desktop_session(BASE_DIR)
    if existing and existing.get("user"):
        return dict(existing["user"])

    from app.local_login_gate import require_blocking_login

    if not require_blocking_login("Start Center"):
        return None

    from app.local_login_gate import get_last_desktop_login

    user = get_last_desktop_login()
    if not user:
        return None
    if not get_active_desktop_session(BASE_DIR):
        create_desktop_session(user, BASE_DIR, source="startup_login")
    return dict(user)


def _run_update_pipeline(splash: StartupSplash, user: dict) -> tuple[bool, str]:
    try:
        from app.program_manifest import APP_VERSION

        splash.set_version(f"Version {APP_VERSION}")
    except Exception:
        splash.set_version("Version check...")
    splash.set_status("Syncing program files from master install...")
    splash.root.update()
    try:
        from app.post_verification_update import run_post_verification_update_pipeline

        splash.set_status("Running install/update + verification (please wait)...")
        code, msg = run_post_verification_update_pipeline(BASE_DIR, user=user)
        if code != 0:
            return True, f"Update finished with warnings (code {code}). Main program will still open.\n{msg[:200]}"
        return True, "Update complete."
    except Exception as exc:
        return True, f"Update step skipped ({exc}). Main program will still open."


def run_program_startup() -> None:
    """Full startup sequence for Launch-JRC-Manager / start_center.main."""
    try:
        from app.host_laptop_roles import is_dedicated_host_install
        from app.runtime_utils import is_jrc_server

        if is_dedicated_host_install(BASE_DIR) and is_jrc_server(8765):
            messagebox.showerror(
                "Dedicated Host PC",
                "The 24/7 host server is already running on this PC.\n\n"
                "Do NOT open Start Center here — it causes 'database is locked'.\n\n"
                "Use only: START JRC Host Server (24-7)\n"
                "Or browse to: http://127.0.0.1:8765/login",
            )
            return
    except Exception:
        pass
    try:
        from app.process_lifecycle import acquire_start_center_lock

        ok, msg = acquire_start_center_lock()
        if not ok:
            messagebox.showerror(
                "JRC Already Running",
                f"{msg}\n\nClose the other JRC window first, or run FIX database lock on the host.",
            )
            return
    except Exception:
        pass
    try:
        from app.db_health import repair_install_database

        ok, msg = repair_install_database(BASE_DIR)
        if not ok:
            messagebox.showerror(
                "Database Repair Needed",
                f"The business database could not be repaired automatically.\n\n{msg[:500]}\n\n"
                "Try closing all JRC windows, then run:\n"
                "  python -m app.db_health --all",
            )
            return
    except Exception as exc:
        try:
            messagebox.showwarning("Database check", f"Could not verify database: {exc}")
        except Exception:
            pass
    try:
        from app.desktop_shortcuts import ensure_desktop_shortcuts_async, read_installer_source

        ensure_desktop_shortcuts_async(BASE_DIR, read_installer_source(BASE_DIR))
    except Exception:
        pass
    try:
        from app.startup_setup import evaluate_setup_state, launch_ensure_venv_hidden

        action, _ = evaluate_setup_state(BASE_DIR)
        if action == "need_venv":
            launch_ensure_venv_hidden(BASE_DIR)
    except Exception:
        pass
    try:
        from app.desktop_session import ensure_session_schema

        ensure_session_schema(BASE_DIR)
    except Exception:
        pass
    try:
        from app.install_live_sync import sync_from_master_if_available

        sync_from_master_if_available(BASE_DIR)
    except Exception:
        pass

    user = _ensure_login()
    if not user:
        return

    splash = StartupSplash(str(user.get("username") or ""))
    result: dict = {"ok": False, "msg": ""}

    def worker() -> None:
        ok, msg = _run_update_pipeline(splash, user)
        result["ok"] = ok
        result["msg"] = msg

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def poll() -> None:
        if t.is_alive():
            splash.root.after(200, poll)
            return
        splash.set_status(result["msg"] or "Starting main program...")
        splash.root.after(400, _open_main)

    def _open_main() -> None:
        splash.close()
        if not result["ok"] and result["msg"]:
            messagebox.showwarning("Startup", result["msg"])
        try:
            from app.desktop_shell import run_embedded_desktop

            if run_embedded_desktop(BASE_DIR, user):
                try:
                    from app.desktop_session import revoke_desktop_session

                    revoke_desktop_session(BASE_DIR, "Program closed")
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            from app.start_center import StartCenter

            app = StartCenter()
        except Exception as exc:
            messagebox.showerror(
                "J & R Construction Manager",
                f"Start Center could not open:\n\n{exc}\n\n"
                "Try: close all JRC windows, then run Launch-JRC-Manager.bat again.",
            )
            return
        try:
            from app.desktop_session import touch_desktop_session

            original_set = app.set_status

            def _set_status(msg: str) -> None:
                touch_desktop_session(BASE_DIR)
                original_set(msg)

            app.set_status = _set_status  # type: ignore[method-assign]
        except Exception:
            pass
        app.mainloop()
        try:
            from app.desktop_session import revoke_desktop_session

            revoke_desktop_session(BASE_DIR, "Program closed")
        except Exception:
            pass

    splash.root.after(200, poll)
    splash.root.mainloop()


def main() -> int:
    run_program_startup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
