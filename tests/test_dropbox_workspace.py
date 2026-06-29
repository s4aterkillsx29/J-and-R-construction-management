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
            records = Path(td) / "workspace"
            reg_dir = records / "08_Admin_Standards"
            reg_dir.mkdir(parents=True)
            (reg_dir / "JRC_JOB_RELATION_REGISTER.csv").write_text(
                "Job_Code,Customer,Address,Status\n", encoding="utf-8"
            )
            old = os.environ.get("JRC_WORKSPACE_ROOT")
            try:
                os.environ["JRC_WORKSPACE_ROOT"] = str(records)
                from app.jrc_workspace import resolve_workspace

                found = resolve_workspace(base)
                self.assertEqual(found, records.resolve())
            finally:
                if old is None:
                    os.environ.pop("JRC_WORKSPACE_ROOT", None)
                else:
                    os.environ["JRC_WORKSPACE_ROOT"] = old


if __name__ == "__main__":
    unittest.main()
