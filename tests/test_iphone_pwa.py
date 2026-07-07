"""iPhone bookmark and PWA smoke tests for J & R Construction Manager."""
from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path


class IPhonePwaTests(unittest.TestCase):
    def _client(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            data_dir = base / "data"
            export_dir = base / "exports"
            evidence_dir = base / "evidence"
            imports_dir = base / "chatgpt_imports"
            backup_dir = base / "backups"
            db_path = data_dir / "jr_business.db"

            env_updates = {
                "JRC_DATA_DIR": str(data_dir),
                "JRC_EXPORT_DIR": str(export_dir),
                "JRC_EVIDENCE_DIR": str(evidence_dir),
                "JRC_CHATGPT_IMPORTS_DIR": str(imports_dir),
                "JRC_BACKUP_DIR": str(backup_dir),
                "JRC_DB_PATH": str(db_path),
                "JRC_PORT": "8765",
                "JRC_ALLOW_LOCAL_DEFAULT_ADMIN": "1",
            }
            old_env = {key: os.environ.get(key) for key in env_updates}
            try:
                os.environ.update(env_updates)
                import app.network_server as ns

                ns = importlib.reload(ns)
                ns.init_db()
                yield ns.app.test_client()
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_mobile_setup_public(self):
        for client in self._client():
            resp = client.get("/mobile/setup")
            self.assertEqual(resp.status_code, 200)
            body = resp.get_data(as_text=True)
            self.assertIn("Add to Home Screen", body)
            self.assertIn("iPhone Setup", body)
            self.assertIn("/mobile", body)

    def test_pwa_manifest_and_icons(self):
        for client in self._client():
            manifest = client.get("/static/manifest.json")
            self.assertEqual(manifest.status_code, 200)
            data = json.loads(manifest.get_data(as_text=True))
            self.assertEqual(data["start_url"], "/mobile")
            self.assertEqual(data["short_name"], "J&R Manager")
            self.assertGreaterEqual(len(data.get("icons", [])), 2)

            for path in (
                "/static/apple-touch-icon.png",
                "/static/pwa-icon-192.png",
                "/static/pwa-icon-512.png",
            ):
                with self.subTest(icon=path):
                    icon = client.get(path)
                    self.assertEqual(icon.status_code, 200)
                    self.assertIn("image/png", icon.content_type)

    def test_layout_includes_pwa_tags(self):
        for client in self._client():
            resp = client.get("/connect")
            body = resp.get_data(as_text=True)
            self.assertIn('rel="manifest"', body)
            self.assertIn("apple-touch-icon", body)
            self.assertIn("serviceWorker.register", body)

    def test_connect_page_iphone_setup_link(self):
        for client in self._client():
            resp = client.get("/connect")
            body = resp.get_data(as_text=True)
            self.assertIn("/mobile/setup", body)
            self.assertIn("iPhone Setup Guide", body)


if __name__ == "__main__":
    unittest.main()
