# -*- coding: utf-8 -*-
"""Mobile outbox processor smoke test."""
from __future__ import annotations

import gc
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path


class MobileOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")
        self.td = tempfile.mkdtemp(prefix="jrc_mobile_outbox_")

    def tearDown(self) -> None:
        gc.collect()
        shutil.rmtree(self.td, ignore_errors=True)

    def test_outbox_schema_and_processor(self) -> None:
        db_path = Path(self.td) / "test.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row
            from app.mobile_platform.outbox_schema import ensure_outbox_schema

            ensure_outbox_schema(conn)
            conn.execute(
                "INSERT INTO mobile_outbox (username, event_type, job_code, payload_json, created_at) VALUES (?,?,?,?,?)",
                ("admin", "note", "JRC-403", '{"note":"test"}', "2026-07-02 23:00:00"),
            )
            conn.commit()
            from app.mobile_platform.outbox_processor import process_pending

            rep = process_pending(conn, Path(self.td))
            self.assertIn("processed", rep)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
