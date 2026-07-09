# -*- coding: utf-8 -*-
"""Button action wrapper — debounce, status feedback, background heavy jobs."""
from __future__ import annotations

import functools
import threading
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def action_guard(label: str = "", *, background: bool = False) -> Callable[[F], F]:
    """Wrap Start Center methods with status updates and optional background thread."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            name = label or fn.__name__.replace("_", " ").title()
            status_fn = getattr(self, "set_status", None)

            def run() -> None:
                try:
                    fn(self, *args, **kwargs)
                    if status_fn:
                        status_fn(f"Done: {name}")
                except Exception as exc:
                    if status_fn:
                        status_fn(f"Error: {name} — {exc}")
                    raise

            if status_fn:
                status_fn(f"Running: {name}...")
            try:
                root = getattr(self, "root", None) or getattr(self, "_root", None)
                if root:
                    root.update_idletasks()
            except Exception:
                pass

            if background:
                threading.Thread(target=run, daemon=True).start()
                return None
            return run()

        return wrapper  # type: ignore[return-value]

    return decorator


# Top 10 Start Center actions wrapped at import (applied in start_center patch)
PRIORITY_ACTIONS = (
    "run_install_or_update",
    "open_office",
    "run_office_records_sync",
    "start_host",
    "start_dedicated_host_easy",
    "run_background_troubleshooter",
    "open_office_ai",
    "open_web_dashboard",
    "run_phase_verification",
    "run_live_full_update",
)
