# Minimal tests for remote_pc_control
import unittest
from unittest.mock import patch

from app.remote_pc_control import (
    _default_host_lan_ip,
    is_office_server_pc,
    probe_tcp,
    run_backdoor_verification,
)


class TestRemotePcControl(unittest.TestCase):
    def test_probe_tcp_closed(self):
        self.assertFalse(probe_tcp("192.0.2.1", 8765, timeout=0.3))

    def test_settings_defaults_exist(self):
        self.assertTrue(_default_host_lan_ip())

    def test_office_server_detect(self):
        with patch.dict("os.environ", {"COMPUTERNAME": "JRConst"}):
            self.assertTrue(is_office_server_pc())

    def test_backdoor_verify_returns_checks(self):
        vr = run_backdoor_verification()
        self.assertIn("checks", vr)
        self.assertGreater(vr.get("total", 0), 5)


if __name__ == "__main__":
    unittest.main()
