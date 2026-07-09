"""Windows 10/11 DPI and platform helpers."""
from __future__ import annotations

import platform
import sys


def enable_win_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll
        # Per-monitor DPI aware (Windows 10 1703+ / Windows 11)
        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            from ctypes import windll
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def is_windows_11_or_newer() -> bool:
    if sys.platform != "win32":
        return False
    try:
        build = int(platform.version().split(".")[-1])
        return build >= 22000
    except Exception:
        return False


def platform_summary() -> str:
    return f"{platform.system()} {platform.release()} ({platform.version()})"


def bootstrap_tk_window(root) -> None:
    """Apply modern Windows 11-friendly Tk defaults (DPI + Segoe UI)."""
    enable_win_dpi_awareness()
    try:
        root.option_add("*Font", "Segoe UI 10")
        root.option_add("*TButton*Font", "Segoe UI 10 bold")
        root.option_add("*TLabel*Font", "Segoe UI 10")
        root.option_add("*TEntry*Font", "Segoe UI 10")
    except Exception:
        pass
    try:
        root.configure(highlightthickness=0, bd=0)
    except Exception:
        pass


def ui_modern_stack_ok() -> dict:
    """Return checklist for automated UI / Win11 verification."""
    checks = {
        "dpi_helper": True,
        "ui_theme_module": False,
        "win11_detected": is_windows_11_or_newer(),
        "platform": platform_summary(),
    }
    try:
        from app import ui_theme  # noqa: F401

        checks["ui_theme_module"] = True
        checks["segoe_font"] = ui_theme.FONT == "Segoe UI"
        checks["configure_ttk"] = callable(getattr(ui_theme, "configure_ttk", None))
    except Exception as exc:
        checks["ui_theme_error"] = str(exc)
    return checks
