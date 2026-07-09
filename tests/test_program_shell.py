# -*- coding: utf-8 -*-
"""Program shell entry smoke test."""
from __future__ import annotations

import os
import unittest


class ProgramShellTests(unittest.TestCase):
    def test_program_shell_import(self) -> None:
        os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")
        import app.program_shell as ps

        self.assertTrue(callable(ps.main))

    def test_ui_actions_priority_list(self) -> None:
        from app.ui_actions import PRIORITY_ACTIONS

        self.assertIn("open_office", PRIORITY_ACTIONS)
        self.assertIn("run_office_records_sync", PRIORITY_ACTIONS)


if __name__ == "__main__":
    unittest.main()
