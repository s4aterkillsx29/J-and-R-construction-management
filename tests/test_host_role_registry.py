"""Unit tests for host_role_registry."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")


class HostRoleRegistryTests(unittest.TestCase):
    def test_default_owner_office(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            data = base / "data"
            data.mkdir()
            os.environ["JRC_DATA_DIR"] = str(data)
            from app.host_role_registry import (
                PC_ROLE_OWNER_OFFICE,
                STRATEGY_LOCAL_EMBEDDED,
                get_host_strategy,
                get_pc_role,
                load_registry,
                pre_start_host_allowed,
                should_show_dedicated_welcome,
            )

            reg = load_registry(base)
            self.assertEqual(reg["pc_role"], PC_ROLE_OWNER_OFFICE)
            self.assertEqual(get_pc_role(base), PC_ROLE_OWNER_OFFICE)
            self.assertEqual(get_host_strategy(base), STRATEGY_LOCAL_EMBEDDED)
            self.assertFalse(should_show_dedicated_welcome(base))
            with patch("app.host_laptop_roles.local_host_is_running", return_value=False):
                ok, msg = pre_start_host_allowed(base)
            self.assertTrue(ok)
            self.assertIn("OK", msg)

    def test_remote_primary_blocks_when_remote_up(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            data = base / "data"
            data.mkdir()
            settings = {
                "pc_role": "owner_office",
                "host_strategy": "remote_primary",
                "remote_host_url": "http://192.168.1.50:8765",
            }
            (data / "local_host_settings.json").write_text(json.dumps(settings), encoding="utf-8")
            os.environ["JRC_DATA_DIR"] = str(data)
            from app.host_role_registry import pre_start_host_allowed

            with patch("app.host_laptop_roles.local_host_is_running", return_value=False):
                with patch(
                    "app.host_laptop_roles.remote_host_is_running",
                    return_value=(True, "http://192.168.1.50:8765", {"version": "8.1.0"}),
                ):
                    ok, msg = pre_start_host_allowed(base)
            self.assertFalse(ok)
            self.assertIn("192.168.1.50", msg)

    def test_poll_interval_on_demand(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            data = base / "data"
            data.mkdir()
            (data / "local_host_settings.json").write_text(
                json.dumps({"host_check_policy": "on_demand"}), encoding="utf-8"
            )
            os.environ["JRC_DATA_DIR"] = str(data)
            from app.host_role_registry import get_poll_interval_ms

            self.assertEqual(get_poll_interval_ms(base), 30000)
            self.assertEqual(get_poll_interval_ms(base, transitioning=True), 5000)


if __name__ == "__main__":
    unittest.main()
