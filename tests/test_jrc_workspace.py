"""Tests for unified J&R business workspace."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class JRCWorkspaceTests(unittest.TestCase):
    def test_resolve_and_save_one_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
            reg = root / "08_Admin_Standards"
            reg.mkdir(parents=True)
            (reg / "JRC_JOB_RELATION_REGISTER.csv").write_text(
                "Job_Code,Customer\n", encoding="utf-8"
            )
            old = os.environ.get("JRC_WORKSPACE_ROOT")
            try:
                os.environ["JRC_WORKSPACE_ROOT"] = str(root)
                from app.jrc_workspace import ensure_unified_workspace, resolve_workspace

                found = resolve_workspace(Path(td) / "install")
                self.assertEqual(found, root.resolve())
                rep = ensure_unified_workspace(Path(td) / "install")
                self.assertTrue(rep["ok"])
                self.assertEqual(rep["workspace"], str(root.resolve()))
            finally:
                if old is None:
                    os.environ.pop("JRC_WORKSPACE_ROOT", None)
                else:
                    os.environ["JRC_WORKSPACE_ROOT"] = old

    def test_dropbox_records_alias_matches_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            (root / "00_START_HERE").mkdir(parents=True)
            (root / "JRC_WORKSPACE.txt").write_text("ok", encoding="utf-8")
            old = os.environ.get("JRC_WORKSPACE_ROOT")
            try:
                os.environ["JRC_WORKSPACE_ROOT"] = str(root)
                from app.jrc_workspace import resolve_business_root, resolve_dropbox_records

                self.assertEqual(resolve_dropbox_records(), root.resolve())
                self.assertEqual(resolve_business_root(), root.resolve())
            finally:
                if old is None:
                    os.environ.pop("JRC_WORKSPACE_ROOT", None)
                else:
                    os.environ["JRC_WORKSPACE_ROOT"] = old


if __name__ == "__main__":
    unittest.main()
