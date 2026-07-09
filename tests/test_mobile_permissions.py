# -*- coding: utf-8 -*-
"""Mobile platform permission / feature matrix tests."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


class MobilePermissionsTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")

    def test_feature_matrix_roles(self) -> None:
        matrix_path = Path(__file__).resolve().parents[1] / "app" / "mobile_platform" / "feature_matrix.json"
        data = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertIn("admin", data)
        self.assertIn("customer", data)
        self.assertIn("home", data["admin"])
        self.assertIn("command_center", data["admin"])
        self.assertNotIn("command_center", data.get("customer", []))

    def test_messenger_customer_isolated(self) -> None:
        from app.messenger import permissions as mp

        self.assertFalse(mp.can_send("customer", "admin_broadcast"))
        self.assertFalse(mp.can_send("customer", "team"))
        self.assertTrue(mp.can_read("customer", "job"))
        self.assertTrue(mp.can_send("worker", "team"))

    def test_outbox_schema_idempotent(self) -> None:
        import sqlite3
        import tempfile

        td = tempfile.mkdtemp(prefix="jrc_mobile_perm_")
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        try:
            from app.mobile_platform.outbox_schema import ensure_outbox_schema

            ensure_outbox_schema(conn)
            ensure_outbox_schema(conn)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("mobile_outbox", tables)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
