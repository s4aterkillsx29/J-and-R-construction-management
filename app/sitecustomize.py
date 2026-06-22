"""
J & R Construction Manager runtime UI refresh.

This file is intentionally small and safe: Python loads sitecustomize automatically
when the app is started from the app folder. It only remaps the older heavy-blue
Tkinter colors to a warmer construction/business palette. Functional code,
business data, network hosting, and login logic are not changed.

Disable for troubleshooting by setting:
    JRC_DISABLE_UI_THEME_PATCH=1
"""
from __future__ import annotations

import os

if os.environ.get("JRC_DISABLE_UI_THEME_PATCH", "").strip().lower() not in {"1", "true", "yes", "on"}:
    try:
        import tkinter as _tk

        _COLOR_MAP = {
            "#07141f": "#11100d",  # old deep blue -> warm charcoal
            "#0b1f2f": "#1b1712",  # panel blue -> dark walnut
            "#12283a": "#251f17",  # card blue -> workbench brown
            "#2f4a60": "#66543a",  # border blue -> brass/wood edge
            "#d7e3ee": "#e8dcc6",  # muted blue-white -> warm paper
            "#9eb4c7": "#b9a98e",  # dim blue-gray -> warm taupe
            "#38bdf8": "#d89b32",  # bright blue info -> amber highlight
            "#1d3a52": "#3a3023",  # button blue -> dark bronze
            "#0f172a": "#17140f",  # entry navy -> near black warm
            "#172554": "#2a2319",
            "#1e3a8a": "#4a341f",
            "#2563eb": "#9a6a24",
            "#37 99 235": "#9a6a24",
            "#60a5fa": "#c88a2f",
        }

        _TITLE_FONT_BUMP = {
            22: 23,
            20: 21,
            18: 19,
            17: 18,
            14: 14,
        }

        def _clean(value):
            if isinstance(value, str):
                return value.strip().lower()
            return value

        def _map_color(value):
            cleaned = _clean(value)
            if isinstance(cleaned, str) and cleaned in _COLOR_MAP:
                return _COLOR_MAP[cleaned]
            return value

        def _map_font(value):
            # Keep the UI familiar, but make headings feel a little more polished.
            if isinstance(value, tuple) and len(value) >= 2:
                family = value[0]
                size = value[1]
                rest = value[2:]
                if family == "Segoe UI" and isinstance(size, int):
                    return (family, _TITLE_FONT_BUMP.get(size, size), *rest)
            return value

        def _map_kwargs(kwargs):
            for key in ("bg", "background", "activebackground", "highlightbackground", "selectbackground", "insertbackground"):
                if key in kwargs:
                    kwargs[key] = _map_color(kwargs[key])
            for key in ("fg", "foreground", "activeforeground", "highlightcolor", "selectforeground"):
                if key in kwargs:
                    kwargs[key] = _map_color(kwargs[key])
            if "font" in kwargs:
                kwargs["font"] = _map_font(kwargs["font"])
            return kwargs

        _orig_init = _tk.Widget.__init__
        _orig_configure = _tk.Widget.configure

        def _patched_init(self, master, widgetName, cnf={}, kw={}, extra=()):
            if isinstance(cnf, dict):
                cnf = _map_kwargs(dict(cnf))
            if isinstance(kw, dict):
                kw = _map_kwargs(dict(kw))
            return _orig_init(self, master, widgetName, cnf, kw, extra)

        def _patched_configure(self, cnf=None, **kw):
            if isinstance(cnf, dict):
                cnf = _map_kwargs(dict(cnf))
            if kw:
                kw = _map_kwargs(dict(kw))
            return _orig_configure(self, cnf, **kw)

        if not getattr(_tk.Widget, "_jrc_theme_patch_applied", False):
            _tk.Widget.__init__ = _patched_init
            _tk.Widget.configure = _patched_configure
            _tk.Widget.config = _patched_configure
            _tk.Widget._jrc_theme_patch_applied = True
    except Exception:
        # Never stop the business app from opening because a visual theme patch failed.
        pass
