"""Static tests for iPhone bookmark helpers (no Flask server required)."""
from __future__ import annotations

import unittest

from app.mobile_phone_setup import mobile_setup_urls, render_mobile_setup_page
from app.pwa_support import PWA_BOOTSTRAP_JS, pwa_head_tags, pwa_manifest_dict


class IPhoneHelperTests(unittest.TestCase):
    def test_mobile_setup_urls(self):
        urls = mobile_setup_urls(lan_ip="192.168.1.50", port=8765)
        self.assertEqual(urls["mobile"], "http://192.168.1.50:8765/mobile")
        self.assertEqual(urls["mobile_setup"], "http://192.168.1.50:8765/mobile/setup")

    def test_render_mobile_setup_page(self):
        html = render_mobile_setup_page(lan_ip="10.0.0.5", port=8765)
        self.assertIn("Add to Home Screen", html)
        self.assertIn("J&amp;R Manager", html)
        self.assertIn("/mobile", html)

    def test_pwa_manifest_start_url(self):
        manifest = pwa_manifest_dict()
        self.assertEqual(manifest["start_url"], "/mobile")
        self.assertGreaterEqual(len(manifest["icons"]), 2)

    def test_pwa_head_tags(self):
        tags = pwa_head_tags()
        self.assertIn("apple-touch-icon", tags)
        self.assertIn("apple-mobile-web-app-capable", tags)

    def test_service_worker_bootstrap(self):
        self.assertIn("serviceWorker.register", PWA_BOOTSTRAP_JS)


if __name__ == "__main__":
    unittest.main()
