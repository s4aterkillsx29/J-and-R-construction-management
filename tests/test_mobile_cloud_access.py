"""Tests for mobile Cursor cloud access point + Dropbox bootstrap helpers."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class MobileCloudAccessTests(unittest.TestCase):
    def test_status_not_ready_without_credentials(self):
        from app import mobile_cloud_access

        old = {
            k: os.environ.pop(k, None)
            for k in (
                "DROPBOX_ACCESS_TOKEN",
                "JRC_DROPBOX_ACCESS_TOKEN",
                "DROPBOX_REFRESH_TOKEN",
                "DROPBOX_APP_KEY",
                "DROPBOX_APP_SECRET",
                "JRC_DROPBOX_RECORDS",
                "JRC_DROPBOX_BUSINESS_ROOT",
            )
        }
        try:
            with tempfile.TemporaryDirectory() as td:
                with mock.patch("app.dropbox_workspace.CLOUD_MIRROR_DIR", Path(td) / "mirror"):
                    with mock.patch("app.dropbox_workspace.BASE_DIR", Path(td)):
                        with mock.patch.object(mobile_cloud_access, "BASE_DIR", Path(td)):
                            report = mobile_cloud_access.status_report()
            self.assertFalse(report["ready"])
            self.assertEqual(report["access"]["mode"], "none")
            self.assertTrue(report["next_steps"])
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_dropbox_api_path_joins_root(self):
        from app.dropbox_workspace import _dropbox_api_path

        old = os.environ.get("DROPBOX_API_ROOT")
        try:
            os.environ["DROPBOX_API_ROOT"] = "/dropbox-records"
            self.assertEqual(
                _dropbox_api_path("08_Admin_Standards/CURRENT_TO_DO.txt"),
                "/dropbox-records/08_Admin_Standards/CURRENT_TO_DO.txt",
            )
        finally:
            if old is None:
                os.environ.pop("DROPBOX_API_ROOT", None)
            else:
                os.environ["DROPBOX_API_ROOT"] = old

    def test_has_refresh_credentials_without_access_token(self):
        from app import dropbox_workspace as dw

        old_token = os.environ.pop("DROPBOX_ACCESS_TOKEN", None)
        old_jrc = os.environ.pop("JRC_DROPBOX_ACCESS_TOKEN", None)
        old_refresh = {
            k: os.environ.get(k)
            for k in ("DROPBOX_REFRESH_TOKEN", "DROPBOX_APP_KEY", "DROPBOX_APP_SECRET")
        }
        try:
            dw._CACHED_ACCESS_TOKEN = None
            os.environ["DROPBOX_REFRESH_TOKEN"] = "rt"
            os.environ["DROPBOX_APP_KEY"] = "key"
            os.environ["DROPBOX_APP_SECRET"] = "secret"
            self.assertTrue(dw.has_dropbox_credentials())
        finally:
            dw._CACHED_ACCESS_TOKEN = None
            if old_token is None:
                os.environ.pop("DROPBOX_ACCESS_TOKEN", None)
            else:
                os.environ["DROPBOX_ACCESS_TOKEN"] = old_token
            if old_jrc is None:
                os.environ.pop("JRC_DROPBOX_ACCESS_TOKEN", None)
            else:
                os.environ["JRC_DROPBOX_ACCESS_TOKEN"] = old_jrc
            for key, value in old_refresh.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_bootstrap_reports_missing_credentials(self):
        from app.dropbox_workspace import bootstrap_essential_mirror

        old = {
            k: os.environ.pop(k, None)
            for k in (
                "DROPBOX_ACCESS_TOKEN",
                "JRC_DROPBOX_ACCESS_TOKEN",
                "DROPBOX_REFRESH_TOKEN",
                "DROPBOX_APP_KEY",
                "DROPBOX_APP_SECRET",
            )
        }
        try:
            from app import dropbox_workspace as dw

            dw._CACHED_ACCESS_TOKEN = None
            report = bootstrap_essential_mirror()
            self.assertFalse(report["ok"])
            self.assertTrue(report["errors"])
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
