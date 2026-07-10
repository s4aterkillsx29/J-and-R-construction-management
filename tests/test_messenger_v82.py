# -*- coding: utf-8 -*-
"""Messenger v8.2 — broadcast read/send split + unread."""
from __future__ import annotations

import unittest

from app.messenger.permissions import allowed_channels, can_read, can_send


class MessengerV82Tests(unittest.TestCase):
    def test_customer_reads_announcements_not_send(self) -> None:
        self.assertIn("admin_broadcast", allowed_channels("customer"))
        self.assertTrue(can_read("customer", "admin_broadcast"))
        self.assertFalse(can_send("customer", "admin_broadcast"))
        self.assertFalse(can_send("customer", "team"))

    def test_worker_reads_not_broadcasts(self) -> None:
        self.assertTrue(can_read("worker", "admin_broadcast"))
        self.assertFalse(can_send("worker", "admin_broadcast"))
        self.assertTrue(can_send("worker", "team"))

    def test_admin_broadcast_send(self) -> None:
        self.assertTrue(can_send("admin", "admin_broadcast"))

    def test_viewer_read_only_team(self) -> None:
        self.assertTrue(can_read("viewer", "admin_broadcast"))
        self.assertFalse(can_send("viewer", "team"))


if __name__ == "__main__":
    unittest.main()
