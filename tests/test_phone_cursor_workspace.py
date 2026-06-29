"""Tests for phone Cursor Dropbox workspace deploy/verify."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class PhoneCursorWorkspaceTests(unittest.TestCase):
    def test_verify_finds_lily_quote(self):
        from app.phone_cursor_workspace import deploy_templates, verify_phone_workspace

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            deploy_templates(root)
            rep = verify_phone_workspace(root)
            self.assertTrue(rep["ok"], rep.get("errors"))
            self.assertTrue(rep["quote_has_amount"])


if __name__ == "__main__":
    unittest.main()
