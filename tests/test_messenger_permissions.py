# -*- coding: utf-8 -*-
"""Messenger role permissions."""
from __future__ import annotations

import unittest

from app.messenger.permissions import allowed_channels, can_read, can_send


class MessengerPermissionTests(unittest.TestCase):
    def test_admin_has_broadcast(self) -> None:
        self.assertIn("admin_broadcast", allowed_channels("admin"))

    def test_customer_isolated(self) -> None:
        self.assertEqual(allowed_channels("customer"), {"job", "admin_broadcast"})
        self.assertFalse(can_send("customer", "team"))
        self.assertFalse(can_send("customer", "admin_broadcast"))

    def test_worker_team_chat(self) -> None:
        self.assertTrue(can_read("worker", "team"))
        self.assertTrue(can_send("helper", "job"))


if __name__ == "__main__":
    unittest.main()
