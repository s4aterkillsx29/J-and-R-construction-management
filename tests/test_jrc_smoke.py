"""Core smoke tests for J & R Construction Manager.

These tests focus on the failures that can stop the program from opening:
- preserved/old SQLite database schema migrations
- local host public endpoint availability
- basic Flask app startup without binding a real TCP port
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class JRCSmokeTests(unittest.TestCase):
    def test_startup_schema_repair_handles_old_file_sources_table(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            data_dir = base / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "jr_business.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE file_sources (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT)")
                conn.commit()

            old_data = os.environ.get("JRC_DATA_DIR")
            old_db = os.environ.get("JRC_DB_PATH")
            try:
                os.environ["JRC_DATA_DIR"] = str(data_dir)
                os.environ["JRC_DB_PATH"] = str(db_path)
                import sitecustomize
                sitecustomize._repair()

                with sqlite3.connect(db_path) as conn:
                    cols = {row[1] for row in conn.execute("PRAGMA table_info(file_sources)").fetchall()}
                    self.assertIn("folder_path", cols)
                    self.assertIn("source_type", cols)
                    self.assertIn("active", cols)
            finally:
                if old_data is None:
                    os.environ.pop("JRC_DATA_DIR", None)
                else:
                    os.environ["JRC_DATA_DIR"] = old_data
                if old_db is None:
                    os.environ.pop("JRC_DB_PATH", None)
                else:
                    os.environ["JRC_DB_PATH"] = old_db

    def test_network_server_import_init_and_public_endpoints(self):
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
                import sitecustomize
                sitecustomize._repair()

                import app.network_server as ns
                ns = importlib.reload(ns)
                ns.init_db()

                client = ns.app.test_client()
                for endpoint in ["/api/health", "/mobile/ping", "/api/connection", "/connect", "/login"]:
                    with self.subTest(endpoint=endpoint):
                        resp = client.get(endpoint)
                        self.assertLess(resp.status_code, 500, endpoint)

                with sqlite3.connect(db_path) as conn:
                    file_cols = {row[1] for row in conn.execute("PRAGMA table_info(file_sources)").fetchall()}
                    app_cols = {row[1] for row in conn.execute("PRAGMA table_info(job_applications)").fetchall()}
                    self.assertIn("folder_path", file_cols)
                    self.assertIn("insurance_full_legal_name", app_cols)
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
