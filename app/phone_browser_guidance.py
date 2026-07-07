"""iPhone browser guidance — Safari is required for LAN access and home-screen bookmarks."""
from __future__ import annotations

import html
from typing import Callable


def detect_phone_browser(user_agent: str = "") -> dict[str, object]:
    ua = (user_agent or "").lower()
    is_iphone = "iphone" in ua or "ipod" in ua
    is_ipad = "ipad" in ua
    is_ios = is_iphone or is_ipad
    is_safari = is_ios and "safari" in ua and "crios" not in ua and "fxios" not in ua and "duckduckgo" not in ua
    is_duckduckgo = "duckduckgo" in ua
    is_chrome_ios = "crios" in ua
    is_firefox_ios = "fxios" in ua
    blocked_for_lan = is_duckduckgo or is_chrome_ios or is_firefox_ios
    name = "Browser"
    if is_duckduckgo:
        name = "DuckDuckGo"
    elif is_chrome_ios:
        name = "Chrome"
    elif is_firefox_ios:
        name = "Firefox"
    elif is_safari:
        name = "Safari"
    elif is_iphone:
        name = "iPhone browser"
    elif is_ipad:
        name = "iPad browser"
    return {
        "is_ios": is_ios,
        "is_safari": is_safari,
        "is_duckduckgo": is_duckduckgo,
        "blocked_for_lan": blocked_for_lan,
        "name": name,
    }


def iphone_browser_warning(
    *,
    user_agent: str = "",
    lan_url: str = "",
    esc: Callable[[object], str] = html.escape,
) -> str:
    info = detect_phone_browser(user_agent)
    if not info["is_ios"]:
        return ""
    if info["is_safari"]:
        return (
            "<div class='card'><p class='ok badge'><b>Safari detected.</b> "
            "You can use this page, sign in, and Add to Home Screen for one-tap access.</p></div>"
        )
    if not info["blocked_for_lan"]:
        return (
            "<div class='card'><p class='yellow badge'><b>iPhone detected.</b> "
            "For best results use <b>Safari</b> to connect and Add to Home Screen.</p></div>"
        )
    browser = esc(str(info["name"]))
    sample = esc(lan_url or "http://YOUR-PC-IP:8765/connect")
    return f"""
    <div class='card'><h2>Use Safari — not {browser}</h2>
      <p class='flash warning'><b>{browser} on iPhone often shows “cannot access that page” for your PC address.</b>
      DuckDuckGo, Chrome, and Firefox on iPhone frequently block or fail on local Wi-Fi links like <code>192.168.x.x</code>.</p>
      <ol>
        <li>Copy this address: <code>{sample}</code></li>
        <li>Open the blue <b>Safari</b> app (compass icon).</li>
        <li>Paste the address in Safari’s address bar and tap Go.</li>
        <li>After it loads, use Share → <b>Add to Home Screen</b> → <b>J&amp;R Manager</b>.</li>
      </ol>
      <p class='muted'>Do <b>not</b> use <code>127.0.0.1</code> or <code>localhost</code> on your phone — that points to the phone itself, not your PC.</p>
    </div>
    """


def iphone_cannot_connect_help(*, esc: Callable[[object], str] = html.escape) -> str:
    return f"""
    <div class='card'><h2>If iPhone says “cannot access” or page won’t load</h2>
      <ol>
        <li><b>Use Safari</b> — not DuckDuckGo, Chrome, or Firefox for the first connection.</li>
        <li><b>Same Wi-Fi</b> — phone and PC must be on the same network (not guest Wi-Fi).</li>
        <li><b>PC host running</b> — Start Center → Start Local Host → wait for verify.</li>
        <li><b>Correct address</b> — use <code>http://PC-LAN-IP:8765/connect</code> from Start Center → Mobile Links.</li>
        <li><b>Firewall</b> — on PC run <b>Allow Phone Access</b>, then restart the host.</li>
        <li><b>Quick test</b> — in Safari try <code>/mobile/ping</code> (should show “J&amp;R mobile connection OK”).</li>
      </ol>
    </div>
    """
