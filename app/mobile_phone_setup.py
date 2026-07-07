"""Owner phone onboarding — mirrors PC post-install setup on mobile browsers."""
from __future__ import annotations

import html
from typing import Callable


def mobile_setup_urls(
    *,
    lan_ip: str,
    port: int,
    remote_base: str = "",
    cloud_base: str = "",
) -> dict[str, str]:
    local = f"http://{lan_ip}:{port}"
    base = (remote_base or cloud_base or local).rstrip("/")
    return {
        "local": local,
        "base": base,
        "connect": f"{base}/connect",
        "login": f"{base}/login",
        "mobile": f"{base}/mobile",
        "mobile_setup": f"{base}/mobile/setup",
        "mobile_jobs": f"{base}/mobile/jobs",
        "mobile_files": f"{base}/mobile/files",
        "register": f"{base}/register",
        "apply": f"{base}/apply",
    }


def render_mobile_setup_page(
    *,
    lan_ip: str,
    port: int,
    remote_base: str = "",
    cloud_base: str = "",
    logged_in: bool = False,
    username: str = "",
    role: str = "",
    esc: Callable[[object], str] = html.escape,
) -> str:
    urls = mobile_setup_urls(
        lan_ip=lan_ip,
        port=port,
        remote_base=remote_base,
        cloud_base=cloud_base,
    )
    using_cloud = bool((remote_base or cloud_base or "").strip())
    access_mode = "Cloud / remote URL" if using_cloud else "Same Wi-Fi local host"
    signed_in = (
        f"<p class='ok badge'>Signed in as <b>{esc(username)}</b> ({esc(role)}).</p>"
        if logged_in
        else "<p class='yellow badge'>Not signed in yet — complete Step 3 below.</p>"
    )
    return f"""
    <div class='card'><h2>J &amp; R Construction — iPhone Setup</h2>
      <p>This page mirrors your <b>PC setup</b> on iPhone: connect, sign in, add the app to your home screen, and open the owner/admin mobile dashboard.</p>
      <p><b>Access mode:</b> {esc(access_mode)}<br>
      <b>Base URL:</b> <code>{esc(urls['base'])}</code></p>
      {signed_in}
    </div>

    <div class='card'><h2>Step 1 — PC must be hosting (same as Start Center)</h2>
      <ol>
        <li>On your PC, open <b>Start Center</b>.</li>
        <li>Click <b>Start Local Host</b> and wait until it verifies.</li>
        <li>If you need phone access away from home Wi-Fi, save your <b>Cloud Access URL</b> in Start Center first.</li>
        <li>If phone fails on same Wi-Fi, run <b>Allow Phone Access</b> on the PC.</li>
      </ol>
    </div>

    <div class='card'><h2>Step 2 — Connection test (do this first on phone)</h2>
      <p>Open this link on your phone. If it loads, the host is reachable.</p>
      <p><a class='btn' href='/connect'>Open Connection Test</a></p>
      <p class='muted'><code>{esc(urls['connect'])}</code></p>
    </div>

    <div class='card'><h2>Step 3 — Sign in with your owner account</h2>
      <p>Use the same owner login you use on the PC — not a worker or customer account.</p>
      <p><a class='btn' href='/login?next=/mobile'>Owner Sign In</a>
      <a class='btn btn2' href='/mobile'>Open Mobile Dashboard</a></p>
      <p class='muted'><code>{esc(urls['login'])}</code></p>
    </div>

    <div class='card'><h2>Step 4 — Add to Home Screen (iPhone bookmark)</h2>
      <p><b>iPhone (Safari):</b> Share button → <b>Add to Home Screen</b> → name it <b>J&amp;R Manager</b>.</p>
      <p><b>Android (Chrome):</b> Menu ⋮ → <b>Add to Home screen</b> or <b>Install app</b>.</p>
      <p>After that, open <b>J&amp;R Manager</b> from your home screen — it opens straight to the mobile dashboard at <code>/mobile</code>.</p>
      <p class='muted'>Bookmark URL: <code>{esc(urls['mobile'])}</code></p>
    </div>

    <div class='card'><h2>Step 5 — Run the business from your phone (owner/admin)</h2>
      <div class='action-grid'>
        <a class='btn' href='/mobile'>Mobile Dashboard</a>
        <a class='btn' href='/mobile/jobs'>Jobs</a>
        <a class='btn' href='/mobile/pipeline'>Job Pipeline</a>
        <a class='btn' href='/mobile/files'>Files / Receipts</a>
        <a class='btn btn2' href='/admin'>Admin Panel</a>
        <a class='btn btn2' href='/jobs'>Full Jobs</a>
        <a class='btn btn2' href='/payroll'>Payroll</a>
        <a class='btn btn2' href='/bookkeeping'>Bookkeeping</a>
      </div>
      <p class='muted'>Owner/admin accounts see money, payroll, and bookkeeping on phone when permissions allow — same database as the PC.</p>
    </div>

    <div class='card'><h2>Troubleshooting</h2>
      <ul>
        <li>Connection test fails → PC host not running, wrong Wi-Fi, or firewall blocked.</li>
        <li>Login works on PC but not phone → run Allow Phone Access on PC, restart host.</li>
        <li>Away from shop → deploy cloud host and save Cloud Access URL on PC first.</li>
        <li>Home screen icon opens login → sign in once; use Remember this phone for 90 days.</li>
      </ul>
    </div>
    """
