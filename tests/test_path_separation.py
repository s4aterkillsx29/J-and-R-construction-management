# -*- coding: utf-8 -*-
"""Verify program/business path separation rules."""
from __future__ import annotations

import os
import unittest


class PathSeparationTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")

    def test_manifest_loads(self) -> None:
        from app.program_paths import load_manifest

        manifest = load_manifest()
        self.assertIn("approved_bridges", manifest)
        self.assertIn("office_records_sync", manifest["approved_bridges"])

    def test_program_path_under_install(self) -> None:
        from app.program_paths import assert_program_path, program_root

        root = program_root()
        ok = assert_program_path(root / "app" / "network_server.py")
        self.assertTrue(ok.is_file() or ok.parent.is_dir())

    def test_forbidden_business_segment_in_program_raises(self) -> None:
        from app.program_paths import assert_program_path, program_root

        bad = program_root() / "data" / "01_Jobs" / "fake"
        with self.assertRaises(ValueError):
            assert_program_path(bad)

    def test_bridge_whitelist(self) -> None:
        from app.program_paths import assert_bridge_allowed

        assert_bridge_allowed("office_records_sync")
        with self.assertRaises(ValueError):
            assert_bridge_allowed("direct_csv_write")

    def test_classify_program_vs_tools(self) -> None:
        from app.program_paths import classify_path, program_root, tools_root

        self.assertEqual(classify_path(program_root() / "app"), "program")
        tr = tools_root()
        if tr.is_dir():
            self.assertEqual(classify_path(tr / "jrc_official_documents.py"), "tools")


if __name__ == "__main__":
    unittest.main()
