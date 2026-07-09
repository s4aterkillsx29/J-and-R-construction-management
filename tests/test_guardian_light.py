# -*- coding: utf-8 -*-
"""Guardian Light profile smoke tests."""
from __future__ import annotations

import os
import unittest


class GuardianLightTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")

    def test_repair_policy_auto_tiers(self) -> None:
        from app.reliability.repair_policy import can_auto_repair, repair_tier

        self.assertEqual(repair_tier("venv_check"), "AUTO")
        self.assertEqual(repair_tier("csv_merge"), "APPROVAL")
        self.assertTrue(can_auto_repair("venv_check", auto_repair_enabled=True))

    def test_consistency_audit_import(self) -> None:
        from app.reliability.consistency_audit import run_read_only_audit

        rep = run_read_only_audit()
        self.assertIn("issues", rep)
        self.assertIn("checks", rep)

    def test_scheduler_light_bounded(self) -> None:
        from app.reliability.guardian_scheduler import GuardianScheduler

        sched = GuardianScheduler()
        result = sched.run_now("light")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("profile"), "light")


if __name__ == "__main__":
    unittest.main()
