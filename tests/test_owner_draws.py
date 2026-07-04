"""Tests for owner draw (paid myself) logging."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class OwnerDrawTests(unittest.TestCase):
    def test_log_owner_draw_dedupes_and_seeds_office_records(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "jr_business.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "INSERT INTO app_settings(key,value) VALUES(?,?)",
                ("std_owner_office_daily_rate", "170"),
            )
            conn.commit()

            from app.owner_draws import (
                ensure_owner_draws_schema,
                log_owner_draw,
                owner_draw_exists,
                seed_owner_draws_from_office_records,
                total_owner_draws,
            )

            ensure_owner_draws_schema(conn)
            ids = seed_owner_draws_from_office_records(conn)
            self.assertEqual(len(ids), 5)
            again = seed_owner_draws_from_office_records(conn)
            self.assertEqual(ids, again)
            self.assertTrue(
                owner_draw_exists(
                    conn,
                    "2026-07-01",
                    170.0,
                    "403 Jackie — business day while Wayne staining",
                )
            )
            self.assertEqual(total_owner_draws(conn), 870.0)

            log_owner_draw(
                conn,
                draw_date="2026-07-05",
                amount=170.0,
                description="Business office full day",
                paid_from_account="Business checking",
                source="test",
            )
            self.assertEqual(total_owner_draws(conn), 1040.0)
            conn.close()

    def test_export_owner_draws_csv(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "jr_business.db"
            out_path = Path(td) / "Owner_Draws_Export_Preview.csv"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.commit()
            from app.owner_draws import (
                ensure_owner_draws_schema,
                export_owner_draws_csv,
                seed_owner_draws_from_office_records,
            )

            ensure_owner_draws_schema(conn)
            seed_owner_draws_from_office_records(conn)
            count = export_owner_draws_csv(conn, out_path)
            self.assertEqual(count, 5)
            text = out_path.read_text(encoding="utf-8")
            self.assertIn("2026-06-29", text)
            self.assertIn("120.00", text)
            self.assertIn("2026-07-01", text)
            self.assertIn("Wayne staining", text)
            conn.close()


if __name__ == "__main__":
    unittest.main()
