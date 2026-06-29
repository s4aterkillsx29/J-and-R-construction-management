"""Tests for Dropbox business workspace resolution."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class DropboxWorkspaceTests(unittest.TestCase):
    def test_dropbox_workspace_resolves_records_from_env(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "install"
            records = Path(td) / "office" / "dropbox-records"
            reg_dir = records / "08_Admin_Standards"
            reg_dir.mkdir(parents=True)
            (reg_dir / "JRC_JOB_RELATION_REGISTER.csv").write_text(
                "Job_Code,Customer,Address,Status\n", encoding="utf-8"
            )
            old = os.environ.get("JRC_DROPBOX_RECORDS")
            try:
                os.environ["JRC_DROPBOX_RECORDS"] = str(records)
                from app.dropbox_workspace import resolve_dropbox_records

                found = resolve_dropbox_records(base)
                self.assertEqual(found, records.resolve())
            finally:
                if old is None:
                    os.environ.pop("JRC_DROPBOX_RECORDS", None)
                else:
                    os.environ["JRC_DROPBOX_RECORDS"] = old

    def test_dropbox_check_reports_no_access_without_sync_or_token(self):
        from app.dropbox_workspace import check_access

        old_token = os.environ.pop("DROPBOX_ACCESS_TOKEN", None)
        old_records = os.environ.pop("JRC_DROPBOX_RECORDS", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                report = check_access(Path(td))
                self.assertIn(report["mode"], ("none", "local"))
                if report["mode"] == "none":
                    self.assertTrue(report["errors"])
        finally:
            if old_token is not None:
                os.environ["DROPBOX_ACCESS_TOKEN"] = old_token
            if old_records is not None:
                os.environ["JRC_DROPBOX_RECORDS"] = old_records


if __name__ == "__main__":
    unittest.main()
