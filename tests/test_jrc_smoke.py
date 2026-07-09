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

# Prevent sitecustomize from touching the live DB before tests set temp paths.
os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")


class JRCSmokeTests(unittest.TestCase):
    def test_startup_schema_repair_handles_old_file_sources_table(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            data_dir = base / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "jr_business.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE file_sources (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT)")
                conn.commit()
            finally:
                conn.close()

            old_data = os.environ.get("JRC_DATA_DIR")
            old_db = os.environ.get("JRC_DB_PATH")
            try:
                os.environ["JRC_DATA_DIR"] = str(data_dir)
                os.environ["JRC_DB_PATH"] = str(db_path)
                import sitecustomize
                sitecustomize._repair()

                conn = sqlite3.connect(db_path)
                try:
                    cols = {row[1] for row in conn.execute("PRAGMA table_info(file_sources)").fetchall()}
                    self.assertIn("folder_path", cols)
                    self.assertIn("source_type", cols)
                    self.assertIn("active", cols)
                finally:
                    conn.close()
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

                with ns.app.app_context():
                    client = ns.app.test_client()
                    for endpoint in ["/api/health", "/mobile/ping", "/api/connection", "/connect", "/login"]:
                        with self.subTest(endpoint=endpoint):
                            resp = client.get(endpoint)
                            self.assertLess(resp.status_code, 500, endpoint)

                conn = sqlite3.connect(db_path)
                try:
                    file_cols = {row[1] for row in conn.execute("PRAGMA table_info(file_sources)").fetchall()}
                    app_cols = {row[1] for row in conn.execute("PRAGMA table_info(job_applications)").fetchall()}
                    self.assertIn("folder_path", file_cols)
                    self.assertIn("insurance_full_legal_name", app_cols)
                finally:
                    conn.close()
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                import gc

                gc.collect()

    def test_workers_schema_bridge_after_network_server_init(self):
        """Desktop Office must open after web host created workers with default_rate."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            data_dir = base / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "jr_business.db"
            env_updates = {
                "JRC_DATA_DIR": str(data_dir),
                "JRC_EXPORT_DIR": str(base / "exports"),
                "JRC_EVIDENCE_DIR": str(base / "evidence"),
                "JRC_CHATGPT_IMPORTS_DIR": str(base / "chatgpt_imports"),
                "JRC_BACKUP_DIR": str(base / "backups"),
                "JRC_DB_PATH": str(db_path),
                "JRC_PORT": "8765",
                "JRC_ALLOW_LOCAL_DEFAULT_ADMIN": "1",
                "JRC_SKIP_STARTUP_REPAIR": "1",
            }
            old_env = {key: os.environ.get(key) for key in env_updates}
            try:
                os.environ.update(env_updates)
                import app.network_server as ns
                ns = importlib.reload(ns)
                ns.init_db()

                conn = sqlite3.connect(db_path)
                try:
                    worker_cols = {row[1] for row in conn.execute("PRAGMA table_info(workers)").fetchall()}
                    self.assertIn("default_rate", worker_cols)
                finally:
                    conn.close()

                from app.schema_migrations import ensure_unified_workers_schema

                conn = sqlite3.connect(db_path)
                try:
                    ensure_unified_workers_schema(conn)
                    worker_cols = {row[1] for row in conn.execute("PRAGMA table_info(workers)").fetchall()}
                    self.assertIn("default_day_rate", worker_cols)
                finally:
                    conn.close()

                import app.jr_job_manager as jm
                jm = importlib.reload(jm)
                db = jm.Database(db_path)
                try:
                    row = db.one("SELECT COUNT(*) AS c FROM workers")
                    self.assertIsNotNone(row)
                    self.assertGreaterEqual(int(row["c"]), 0)
                finally:
                    if hasattr(db, "conn") and db.conn:
                        db.conn.close()
                import gc
                gc.collect()
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_office_ai_tax_tool_imports_and_registry(self):
        import importlib

        tax_tool = importlib.import_module("app.office_ai.tools.office_mgmt_check_tax_savings_plan")
        receipt_tool = importlib.import_module("app.office_ai.tools.save_receipt_note")
        registry = importlib.import_module("app.office_ai.tool_registry")

        self.assertTrue(hasattr(tax_tool, "run"))
        self.assertTrue(hasattr(receipt_tool, "run"))
        self.assertIn("check_tax_savings_plan", registry._TOOL_MODULES)
        self.assertIn("save_receipt_note", registry._TOOL_MODULES)
        result = tax_tool.run()
        self.assertIn("ok", result)


if __name__ == "__main__":
    unittest.main()
