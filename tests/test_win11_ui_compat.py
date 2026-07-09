"""Windows 11 UI compatibility checks."""
from __future__ import annotations

import os
import unittest


class Win11UICompatTests(unittest.TestCase):
    def test_ui_modern_stack(self) -> None:
        from app.win11_compat import ui_modern_stack_ok

        rep = ui_modern_stack_ok()
        self.assertTrue(rep["dpi_helper"])
        self.assertTrue(rep["ui_theme_module"])
        self.assertEqual(rep.get("segoe_font"), True)
        self.assertTrue(rep.get("configure_ttk"))

    # Start Center theme covered by tests/test_start_center_build.py (avoids Tk flake in full suite)

    def test_ui_theme_configures_ttk(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        from app import ui_theme
        from app.win11_compat import bootstrap_tk_window

        root = tk.Tk()
        try:
            bootstrap_tk_window(root)
            style = ttk.Style(root)
            ui_theme.configure_ttk(style)
            self.assertEqual(style.theme_use(), "clam")
            font_val = style.configure("TLabel", "font")
            self.assertIn("Segoe UI", str(font_val))
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
