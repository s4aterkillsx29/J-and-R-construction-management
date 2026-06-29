"""Tests for full workspace log/sync pipeline."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class WorkspaceSyncTests(unittest.TestCase):
    def test_standards_sync_both_directions(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "install"
            ws = Path(td) / "workspace"
            (ws / "08_Admin_Standards").mkdir(parents=True)
            (ws / "00_START_HERE").mkdir(parents=True)
            (ws / "08_Admin_Standards" / "DOCUMENT_GENERATION_STANDARDS.txt").write_text(
                "office doc standard", encoding="utf-8"
            )
            std = base / "business_standards"
            std.mkdir(parents=True)
            (std / "JRC_Business_Document_Standards.json").write_text("{}", encoding="utf-8")

            from app.workspace_sync import (
                sync_standards_install_to_workspace,
                sync_standards_workspace_to_install,
            )

            notes_in = sync_standards_workspace_to_install(ws, base)
            self.assertTrue(any("DOCUMENT_GENERATION" in n for n in notes_in))
            self.assertTrue((base / "business_standards" / "DOCUMENT_GENERATION_STANDARDS.txt").is_file())

            notes_out = sync_standards_install_to_workspace(ws, base)
            self.assertTrue(
                (ws / "08_Admin_Standards" / "JRC_Business_Document_Standards.json").is_file()
            )
            self.assertTrue(any("pushed" in n for n in notes_out))

    def test_dashboard_and_sync_log_written(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            (ws / "00_START_HERE" / "READABLE").mkdir(parents=True)
            report = {"ok": True, "workspace": str(ws), "notes": ["test"], "errors": []}
            from app.workspace_sync import append_sync_log, write_business_dashboard

            dash = write_business_dashboard(ws, report)
            self.assertTrue(dash.is_file())
            self.assertIn("Last PC sync", dash.read_text(encoding="utf-8"))
            log = append_sync_log(ws, report)
            self.assertTrue(log.is_file())
            self.assertTrue((ws / "00_START_HERE" / "READABLE" / "LAST_SYNC.json").is_file())


if __name__ == "__main__":
    unittest.main()
