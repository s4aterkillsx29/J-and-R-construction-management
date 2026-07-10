# -*- coding: utf-8 -*-
"""Session root agreement + rooted tracking tests."""
from __future__ import annotations

import sqlite3
import unittest

from app.session_root_tracking import (
    AGREEMENT_FIELD,
    agreement_checked,
    ensure_root_session_schema,
    is_owner_account,
    record_session_root_tracking,
)


class SessionRootTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE online_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER,
                username TEXT,
                role TEXT,
                ip_address TEXT,
                user_agent TEXT,
                login_time TEXT,
                last_seen TEXT,
                active INTEGER DEFAULT 1,
                revoked INTEGER DEFAULT 0
            )
            """
        )
        self.conn.execute(
            "INSERT INTO online_sessions (session_id, user_id, username, role, ip_address, user_agent, login_time, last_seen) "
            "VALUES ('s1', 2, 'worker1', 'worker', '1.2.3.4', 'test', 'now', 'now')"
        )
        self.conn.commit()
        self.events: list[str] = []

    def _log(self, event_type: str, username: str = "", message: str = "", level: str = "INFO") -> None:
        self.events.append(event_type)

    def test_agreement_field_name(self) -> None:
        self.assertEqual(AGREEMENT_FIELD, "root_device_agreement")

    def test_agreement_checked(self) -> None:
        self.assertTrue(agreement_checked("1"))
        self.assertFalse(agreement_checked(None))

    def test_owner_detection(self) -> None:
        self.assertTrue(is_owner_account({"username": "admin", "owner_account": 1}))
        self.assertFalse(is_owner_account({"username": "worker1", "owner_account": 0}))

    def test_non_owner_rooted_session_logged(self) -> None:
        ensure_root_session_schema(self.conn)
        user = {"id": 2, "username": "worker1", "role": "worker", "owner_account": 0}
        result = record_session_root_tracking(
            self.conn,
            session_id="s1",
            user=user,
            ip_address="1.2.3.4",
            user_agent="Mozilla",
            device_label="Phone",
            device_fingerprint="abc",
            root_agreed=True,
            login_source="web_form",
            log_security_event=self._log,
        )
        self.conn.commit()
        self.assertTrue(result["rooted"])
        row = self.conn.execute(
            "SELECT username, active FROM rooted_live_sessions WHERE session_id='s1'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["username"], "worker1")
        self.assertIn("rooted_session_started", self.events)

    def test_owner_not_rooted(self) -> None:
        ensure_root_session_schema(self.conn)
        user = {"id": 1, "username": "admin", "role": "admin", "owner_account": 1}
        result = record_session_root_tracking(
            self.conn,
            session_id="s1",
            user=user,
            ip_address="127.0.0.1",
            user_agent="PC",
            device_label="Desktop",
            device_fingerprint="",
            root_agreed=True,
            login_source="web_form",
            log_security_event=self._log,
        )
        self.conn.commit()
        self.assertFalse(result["rooted"])
        count = self.conn.execute("SELECT COUNT(*) FROM rooted_live_sessions").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
