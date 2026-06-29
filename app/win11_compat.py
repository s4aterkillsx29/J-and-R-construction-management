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
