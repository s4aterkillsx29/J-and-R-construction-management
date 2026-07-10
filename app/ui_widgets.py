# -*- coding: utf-8 -*-
"""Shared in-app UI widgets — messenger drawer + admin popup shell."""
from __future__ import annotations

import html
from typing import Optional


def build_messenger_widget(*, username: str, role: str, enabled: bool = True) -> str:
    """Floating live chat drawer for all signed-in users with dashboard access."""
    if not enabled or not username:
        return ""
    safe_user = html.escape(username)
    safe_role = html.escape(role or "")
    return f"""
<div id="jrc-messenger-root" data-username="{safe_user}" data-role="{safe_role}">
  <button type="button" id="jrc-messenger-toggle" aria-label="Live Chat" title="Live Chat">
    <span class="jrc-msg-icon">💬</span>
    <span class="jrc-msg-label">Chat</span>
    <span id="jrc-messenger-badge" class="jrc-msg-badge" hidden>0</span>
  </button>
  <div id="jrc-messenger-drawer" aria-hidden="true">
    <header class="jrc-msg-header">
      <strong>Live Chat</strong>
      <button type="button" id="jrc-messenger-close" aria-label="Close">×</button>
    </header>
    <div id="jrc-messenger-sessions" class="jrc-msg-sessions"></div>
    <div id="jrc-messenger-thread" class="jrc-msg-thread" hidden>
      <div class="jrc-msg-thread-head">
        <button type="button" id="jrc-messenger-back" class="jrc-msg-back">← Sessions</button>
        <span id="jrc-messenger-thread-title"></span>
      </div>
      <div id="jrc-messenger-messages" class="jrc-msg-messages"></div>
      <form id="jrc-messenger-compose" class="jrc-msg-compose">
        <textarea id="jrc-messenger-input" rows="2" placeholder="Type a message…" required></textarea>
        <button type="submit">Send</button>
      </form>
    </div>
    <footer class="jrc-msg-footer">
      <a href="/mobile/messages">Full mobile chat</a>
      <a href="/chat">Open full page</a>
    </footer>
  </div>
</div>
<link rel="stylesheet" href="/static/messenger.css">
<script src="/static/messenger.js" defer></script>
"""


def build_admin_popup_shell(*, is_admin: bool) -> str:
    """Modal overlay system for admin user/session quick actions."""
    if not is_admin:
        return ""
    return """
<div id="jrc-admin-modal" class="jrc-modal" hidden aria-hidden="true">
  <div class="jrc-modal-backdrop" data-jrc-modal-close></div>
  <div class="jrc-modal-panel" role="dialog" aria-labelledby="jrc-admin-modal-title">
    <header class="jrc-modal-header">
      <h2 id="jrc-admin-modal-title">User Actions</h2>
      <button type="button" class="jrc-modal-close" data-jrc-modal-close aria-label="Close">×</button>
    </header>
    <div id="jrc-admin-modal-body" class="jrc-modal-body"></div>
    <footer class="jrc-modal-footer">
      <button type="button" class="btn btn2" data-jrc-modal-close>Close</button>
    </footer>
  </div>
</div>
<link rel="stylesheet" href="/static/admin-popups.css">
<script src="/static/admin-popups.js" defer></script>
"""
