"""PWA and iPhone home-screen bookmark support for J&R Construction Manager."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parents[1]
PWA_ICON_PATH = BASE_DIR / "assets" / "j_and_r_manager_icon.png"

PWA_BOOTSTRAP_JS = (
    "if('serviceWorker' in navigator){"
    "navigator.serviceWorker.register('/static/service-worker.js').catch(function(){});}"
)


def pwa_head_tags() -> str:
    return (
        '<link rel="manifest" href="/static/manifest.json">'
        '<meta name="theme-color" content="#84cc16">'
        '<meta name="apple-mobile-web-app-capable" content="yes">'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'
        '<meta name="apple-mobile-web-app-title" content="J&R Manager">'
        '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">'
        '<link rel="icon" type="image/png" sizes="192x192" href="/static/pwa-icon-192.png">'
    )


def pwa_manifest_dict() -> dict:
    return {
        "name": "J and R Construction Manager",
        "short_name": "J&R Manager",
        "start_url": "/mobile",
        "scope": "/",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#84cc16",
        "description": "Mobile access for J and R Construction Manager jobs, files, and shared sessions.",
        "icons": [
            {
                "src": "/static/pwa-icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/pwa-icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }


def owner_iphone_bookmark_card(
    *,
    mobile_url: str,
    setup_url: str,
    esc: Callable[[object], str],
) -> str:
    return f"""
    <div class='card'><h2>iPhone Quick Access (Owner/Admin)</h2>
      <p>Add <b>J&amp;R Manager</b> to your iPhone home screen for one-tap access to this mobile dashboard.</p>
      <ol>
        <li>Open this page in <b>Safari</b> (not Chrome).</li>
        <li>Tap <b>Share</b> → <b>Add to Home Screen</b> → name it <b>J&amp;R Manager</b>.</li>
        <li>Open the new icon — it launches straight to <code>/mobile</code> after you sign in.</li>
      </ol>
      <p><b>Bookmark URL:</b><br><code>{esc(mobile_url)}</code></p>
      <p><a class='btn' href='/mobile/setup'>Full Phone Setup Guide</a>
      <a class='btn btn2' href='/admin'>Admin Panel</a></p>
      <p class='muted'>Setup guide: <code>{esc(setup_url)}</code></p>
    </div>
    """
