# -*- coding: utf-8 -*-
"""Mobile messages + capture routes — polished phone UI."""
from __future__ import annotations

import html
from typing import Callable

from flask import request


def register_mobile_page_routes(
    app,
    *,
    db_fn: Callable,
    login_required: Callable,
    layout: Callable,
    current_user: Callable,
    normalize_role: Callable,
) -> None:
    """Register /mobile/messages and /mobile/capture."""

    def _mobile_nav(active: str) -> str:
        tabs = [
            ("home", "Home", "/mobile"),
            ("jobs", "Jobs", "/mobile/jobs"),
            ("messages", "Chat", "/mobile/messages"),
            ("capture", "Capture", "/mobile/capture"),
            ("files", "Files", "/mobile/files"),
        ]
        links = "".join(
            f'<a href="{href}" class="mob-nav-item{" active" if key == active else ""}">{label}</a>'
            for key, label, href in tabs
        )
        return f'<nav class="mob-bottom-nav">{links}</nav>'

    def _mobile_shell(title: str, body: str, nav: str = "home") -> str:
        return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#84cc16">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="J&amp;R Manager">
<title>{html.escape(title)} — J&amp;R Mobile</title>
<link rel="manifest" href="/static/manifest.json">
<link rel="stylesheet" href="/static/mobile/mobile.css">
</head>
<body class="mob-body" data-nav="{html.escape(nav)}">
<header class="mob-header"><h1>{html.escape(title)}</h1></header>
<main class="mob-main">{body}</main>
{_mobile_nav(nav)}
<script src="/static/mobile/mobile-outbox.js"></script>
<script src="/static/mobile/mobile-app.js"></script>
<script src="/static/messenger.js" defer></script>
</body></html>"""

    @app.route("/mobile/messages")
    @login_required("view_dashboard")
    def mobile_messages():
        user = current_user()
        role = normalize_role(user.get("role", ""))
        safe_user = html.escape(user.get("username", ""))
        safe_role = html.escape(role)
        body = f"""
        <div id="jrc-mobile-chat" data-username="{safe_user}" data-role="{safe_role}" data-mobile="1">
          <div id="jrc-messenger-sessions" class="jrc-msg-sessions mob-sessions"></div>
          <div id="jrc-messenger-thread" class="jrc-msg-thread mob-thread">
            <div class="jrc-msg-thread-head">
              <button type="button" id="jrc-messenger-back" class="jrc-msg-back">← Back</button>
              <span id="jrc-messenger-thread-title">Select a chat</span>
            </div>
            <div id="jrc-messenger-messages" class="jrc-msg-messages"></div>
            <form id="jrc-messenger-compose" class="jrc-msg-compose">
              <textarea id="jrc-messenger-input" rows="2" placeholder="Message…" required></textarea>
              <button type="submit">Send</button>
            </form>
          </div>
        </div>
        <link rel="stylesheet" href="/static/messenger.css">
        """
        return _mobile_shell("Live Chat", body, "messages")

    @app.route("/mobile/capture")
    @login_required("view_dashboard")
    def mobile_capture():
        body = """
        <section class="mob-card">
          <h2>Field Capture</h2>
          <p class="muted">Save notes and photos to the mobile outbox — syncs to Dropbox job folders when online.</p>
          <form id="mob-capture-form" class="mob-form">
            <label>Job code (optional)</label>
            <input name="job_code" placeholder="JRC-403" autocomplete="off">
            <label>Note</label>
            <textarea name="note" rows="4" placeholder="Jobsite note, material list, etc."></textarea>
            <label>Photo (optional)</label>
            <input type="file" name="photo" accept="image/*" capture="environment">
            <button type="submit" class="mob-btn">Queue for sync</button>
          </form>
          <p id="mob-capture-status" class="muted"></p>
        </section>
        <script>
        (function(){
          var form = document.getElementById("mob-capture-form");
          var status = document.getElementById("mob-capture-status");
          if (!form) return;
          form.addEventListener("submit", function(e){
            e.preventDefault();
            var fd = new FormData(form);
            var payload = { note: fd.get("note")||"", job_code: fd.get("job_code")||"" };
            var file = fd.get("photo");
            function queue(item){
              if (window.JRCMobileOutbox && window.JRCMobileOutbox.enqueue) {
                window.JRCMobileOutbox.enqueue(item).then(function(){
                  status.textContent = "Queued — will sync when online.";
                  form.reset();
                }).catch(function(){ status.textContent = "Queue failed — try again."; });
              } else {
                fetch("/api/mobile/outbox/batch", {
                  method:"POST", headers:{"Content-Type":"application/json"},
                  body: JSON.stringify({ items: [item] })
                }).then(function(r){ return r.json(); }).then(function(d){
                  status.textContent = d.ok ? "Saved to server outbox." : "Save failed.";
                  if (d.ok) form.reset();
                });
              }
            }
            if (file && file.size) {
              var reader = new FileReader();
              reader.onload = function(){
                payload.photo_name = file.name;
                payload.photo_data = reader.result;
                queue({ event_type:"photo", job_code: payload.job_code, payload: payload });
              };
              reader.readAsDataURL(file);
            } else {
              queue({ event_type:"note", job_code: payload.job_code, payload: payload });
            }
          });
        })();
        </script>
        """
        return _mobile_shell("Field Capture", body, "capture")
