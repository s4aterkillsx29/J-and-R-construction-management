# -*- coding: utf-8 -*-
"""Ensure Start Center UI builds without crashing."""
from __future__ import annotations

import os
import unittest


class StartCenterBuildTests(unittest.TestCase):
    def test_start_center_builds_ui(self) -> None:
        os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")
        import tkinter as tk

        from app.start_center import StartCenter

        app = StartCenter()
        try:
            self.assertTrue(hasattr(app, "_admin_dock"))
            self.assertTrue(hasattr(app, "_cards_frame"))
            self.assertTrue(hasattr(app, "_sections"))
            self.assertIn("daily", app._sections)
            children = app._cards_frame.winfo_children()
            self.assertGreater(len(children), 0, "Home section should render action cards")
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
