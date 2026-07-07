"""Static tests for iPhone bookmark helpers (no Flask server required)."""
from __future__ import annotations

import unittest

from app.mobile_phone_setup import mobile_setup_urls, render_mobile_setup_page
from app.phone_browser_guidance import detect_phone_browser, iphone_browser_warning
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

    def test_detect_duckduckgo_blocks_lan(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 DuckDuckGo/7"
        info = detect_phone_browser(ua)
        self.assertTrue(info["is_duckduckgo"])
        self.assertTrue(info["blocked_for_lan"])
        warning = iphone_browser_warning(user_agent=ua, lan_url="http://192.168.1.10:8765/connect")
        self.assertIn("DuckDuckGo", warning)
        self.assertIn("Safari", warning)

    def test_detect_safari_ok(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        info = detect_phone_browser(ua)
        self.assertTrue(info["is_safari"])
        warning = iphone_browser_warning(user_agent=ua)
        self.assertIn("Safari detected", warning)


if __name__ == "__main__":
    unittest.main()
