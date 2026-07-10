# -*- coding: utf-8 -*-
"""Admin popup module import smoke."""
from __future__ import annotations

import unittest


class AdminPopupsSmokeTests(unittest.TestCase):
    def test_register_import(self) -> None:
        from app.admin_popups import register_admin_popup_routes

        self.assertTrue(callable(register_admin_popup_routes))

    def test_ui_widgets(self) -> None:
        from app.ui_widgets import build_admin_popup_shell, build_messenger_widget

        html = build_messenger_widget(username="jacob", role="admin", enabled=True)
        self.assertIn("jrc-messenger-root", html)
        admin = build_admin_popup_shell(is_admin=True)
        self.assertIn("jrc-admin-modal", admin)
        self.assertEqual(build_admin_popup_shell(is_admin=False), "")


if __name__ == "__main__":
    unittest.main()
