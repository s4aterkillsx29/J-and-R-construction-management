"""Unit tests for server_control."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")


class ServerControlTests(unittest.TestCase):
    def test_get_status_not_running(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            data = base / "data"
            data.mkdir()
            os.environ["JRC_DATA_DIR"] = str(data)
            with patch("app.server_control.is_running", return_value=False):
                from app.server_control import get_status

                st = get_status(base)
            self.assertFalse(st["running"])
            self.assertIn("port", st)
            self.assertIn("role_display", st)

    def test_tail_logs_missing_file(self):
        from app.server_control import tail_logs

        text = tail_logs(10, log_path=Path("/nonexistent/shared_host_last.log"))
        self.assertIn("No log file", text)

    def test_tail_logs_reads_lines(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "test.log"
            log.write_text("line1\nline2\nline3\n", encoding="utf-8")
            from app.server_control import tail_logs

            text = tail_logs(2, log_path=log)
            self.assertIn("line2", text)
            self.assertIn("line3", text)
            self.assertNotIn("line1", text)

    def test_start_server_already_running(self):
        with patch("app.server_control.is_running", return_value=True):
            from app.server_control import start_server

            result = start_server()
        self.assertTrue(result["ok"])
        self.assertFalse(result["started"])


if __name__ == "__main__":
    unittest.main()
