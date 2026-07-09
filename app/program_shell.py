# -*- coding: utf-8 -*-
"""Unified program entry — login → update splash → Start Center (one process)."""
from __future__ import annotations

import os
import sys


def main() -> int:
    """v8 unified shell entry. Set JRC_USE_PROGRAM_SHELL=0 to use legacy start_center only."""
    if os.environ.get("JRC_USE_PROGRAM_SHELL", "1").strip() in {"0", "false", "no"}:
        from app.start_center import main as sc_main

        sc_main()
        return 0

    try:
        from app.reliability.guardian_scheduler import get_scheduler
        from app.startup_bootstrap import run_program_startup

        sched = get_scheduler()
        sched.start()
        run_program_startup()
    except Exception as exc:
        try:
            from tkinter import messagebox

            messagebox.showerror("J & R Construction Manager", f"Startup failed: {exc}")
        except Exception:
            print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
