"""Tests for Dropbox sync mirror bootstrap."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class DropboxSyncTests(unittest.TestCase):
    def test_sync_bootstraps_mirror_and_resolves_records(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "repo"
            mirror = Path(td) / "mirror"
            templates = base / "scripts" / "templates" / "dropbox_workspace"
            reg = templates / "08_Admin_Standards"
            reg.mkdir(parents=True)
            (reg / "JRC_JOB_RELATION_REGISTER.csv").write_text(
                "Job_Code,Customer,Address,Status\nJRC-403,Jackie,403 East 2nd,Active\n",
                encoding="utf-8",
            )
            old_mirror = os.environ.get("JRC_DROPBOX_MIRROR")
            old_token = os.environ.pop("DROPBOX_ACCESS_TOKEN", None)
            try:
                os.environ["JRC_DROPBOX_MIRROR"] = str(mirror)
                from app.dropbox_workspace import resolve_dropbox_records, sync_dropbox_mirror

                report = sync_dropbox_mirror(base)
                self.assertFalse(report.get("errors"), msg=report.get("errors"))
                found = resolve_dropbox_records(base)
                self.assertIsNotNone(found)
                self.assertTrue((found / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv").is_file())
            finally:
                if old_mirror is None:
                    os.environ.pop("JRC_DROPBOX_MIRROR", None)
                else:
                    os.environ["JRC_DROPBOX_MIRROR"] = old_mirror
                if old_token is not None:
                    os.environ["DROPBOX_ACCESS_TOKEN"] = old_token


if __name__ == "__main__":
    unittest.main()
