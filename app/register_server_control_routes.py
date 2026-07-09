# -*- coding: utf-8 -*-
"""Flask routes for unified admin server control."""
from __future__ import annotations

import html
from typing import Callable


def register_server_control_routes(
    app,
    *,
    login_required: Callable,
    layout: Callable,
    base_dir,
    APP_VERSION: str = "",
) -> None:
    from flask import jsonify, request

    from app import server_control
    from app.host_role_registry import (
        PC_ROLE_DEDICATED_HOST,
        PC_ROLE_OWNER_OFFICE,
        PC_ROLE_REMOTE_CLIENT,
        STRATEGY_CLOUD_PRIMARY,
        STRATEGY_LOCAL_EMBEDDED,
        STRATEGY_REMOTE_PRIMARY,
        confirm_pc_role,
        load_registry,
    )

    ver = APP_VERSION or "8.1.0"

    @app.route("/admin/server")
    @login_required("view_admin")
    def admin_server_page():
        st = server_control.get_status(base_dir)
        links = server_control.share_links(base_dir)
        running = st.get("running")
        badge = "ok" if running else "red"
        state = "RUNNING" if running else "STOPPED"
        link_rows = "".join(
            f"<tr><td>{html.escape(label)}</td><td><code>{html.escape(url)}</code></td>"
            f"<td><button type='button' class='btn btn2 copy-link' data-url='{html.escape(url)}'>Copy</button></td></tr>"
            for label, url in (
                ("Mobile", links.get("mobile", "")),
                ("Connect test", links.get("connect", "")),
                ("Register", links.get("register", "")),
                ("Apply", links.get("apply", "")),
            )
        )
        reg = load_registry(base_dir)
        body = f"""
        <div class="card"><h2>Server Control Center</h2>
          <p class="muted">v{html.escape(ver)} · Start, stop, monitor, and share links from one place.</p>
          <div class="grid">
            <div class="stat">Status<span class="badge {badge}">{state}</span>
              <span class="muted">Port {html.escape(str(st.get('port','?')))} · PID {html.escape(str(st.get('pid') or '—'))}<br>
              LAN: <code>{html.escape(st.get('lan_url',''))}</code><br>
              Cloud: {html.escape(st.get('cloud_url') or 'not configured')}</span></div>
            <div class="stat">Sessions<span class="badge ok">{html.escape(str(st.get('sessions_count',0)))}</span>
              <span class="muted">Active browser sessions on this host</span></div>
            <div class="stat">PC Role<span class="badge ok">{html.escape(st.get('pc_role',''))}</span>
              <span class="muted">{html.escape(st.get('role_display',''))}</span></div>
          </div>
        </div>
        <div class="card"><h2>Controls</h2>
          <p>
            <button type="button" class="btn" id="srv-start">Start</button>
            <button type="button" class="btn warn" id="srv-stop">Stop</button>
            <button type="button" class="btn btn2" id="srv-restart">Restart</button>
            <button type="button" class="btn btn2" id="srv-firewall">Allow LAN (Firewall)</button>
            <a class="btn btn2" href="/admin">Admin Home</a>
            <a class="btn btn2" href="/hosting">Hosting Info</a>
          </p>
          <pre id="srv-msg" class="muted" style="white-space:pre-wrap;max-height:120px;overflow:auto"></pre>
        </div>
        <div class="card"><h2>Active Sessions</h2>
          <div id="srv-sessions"><p class="muted">Loading…</p></div>
        </div>
        <div class="card"><h2>Share Links</h2>
          <table style="width:100%;border-collapse:collapse">
            <tr><th align="left">Link</th><th align="left">URL</th><th></th></tr>
            {link_rows}
          </table>
        </div>
        <div class="card"><h2>Host Log (tail)</h2>
          <pre id="srv-logs" style="max-height:280px;overflow:auto;background:rgba(0,0,0,.35);padding:12px;border-radius:12px;font-size:12px"></pre>
          <button type="button" class="btn btn2" id="srv-refresh-logs">Refresh Logs</button>
        </div>
        <div class="card"><h2>Confirm PC Role (one-time)</h2>
          <p class="muted">Set once — stops repeated 24/7 host prompts on office PC. Confirmed: {html.escape(str(reg.get('role_confirmed_at') or 'not yet'))}</p>
          <form id="srv-role-form" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
            <p><label>PC role</label>
              <select name="pc_role" id="srv-pc-role">
                <option value="{PC_ROLE_OWNER_OFFICE}">Owner office PC</option>
                <option value="{PC_ROLE_DEDICATED_HOST}">Dedicated 24/7 host</option>
                <option value="{PC_ROLE_REMOTE_CLIENT}">Remote client only</option>
              </select></p>
            <p><label>Host strategy</label>
              <select name="host_strategy" id="srv-host-strategy">
                <option value="{STRATEGY_LOCAL_EMBEDDED}">Local embedded</option>
                <option value="{STRATEGY_REMOTE_PRIMARY}">Remote primary</option>
                <option value="{STRATEGY_CLOUD_PRIMARY}">Cloud primary</option>
              </select></p>
            <button type="submit" class="btn">Save Role</button>
          </form>
        </div>
        <script>
        (function(){{
          const msg = document.getElementById('srv-msg');
          function api(path, method) {{
            return fetch(path, {{method: method || 'GET', headers: {{'Content-Type':'application/json'}}}})
              .then(r => r.json()).then(d => {{ msg.textContent = d.message || JSON.stringify(d); return d; }});
          }}
          document.getElementById('srv-start').onclick = () => api('/api/admin/server/start','POST');
          document.getElementById('srv-stop').onclick = () => {{ if(confirm('Stop local host?')) api('/api/admin/server/stop','POST').then(refreshSessions); }};
          document.getElementById('srv-restart').onclick = () => api('/api/admin/server/restart','POST').then(refreshSessions);
          document.getElementById('srv-firewall').onclick = () => api('/api/admin/server/firewall','POST');
          document.getElementById('srv-refresh-logs').onclick = refreshLogs;
          document.querySelectorAll('.copy-link').forEach(btn => {{
            btn.onclick = () => {{ navigator.clipboard.writeText(btn.dataset.url); msg.textContent = 'Copied: ' + btn.dataset.url; }};
          }});
          function refreshSessions() {{
            fetch('/api/admin/server/sessions').then(r=>r.json()).then(d => {{
              const box = document.getElementById('srv-sessions');
              const rows = (d.sessions||[]).map(s =>
                `<div>${{s.username||'?'}} (${{s.role||''}}) — ${{s.ip_address||''}}</div>`).join('');
              box.innerHTML = rows || '<p class="muted">No active sessions</p>';
            }});
          }}
          function refreshLogs() {{
            fetch('/api/admin/server/logs?tail=80').then(r=>r.json()).then(d => {{
              document.getElementById('srv-logs').textContent = d.text || '';
            }});
          }}
          document.getElementById('srv-role-form').onsubmit = (e) => {{
            e.preventDefault();
            fetch('/api/admin/server/role', {{
              method:'POST',
              headers:{{'Content-Type':'application/json'}},
              body: JSON.stringify({{
                pc_role: document.getElementById('srv-pc-role').value,
                host_strategy: document.getElementById('srv-host-strategy').value
              }})
            }}).then(r=>r.json()).then(d => {{ msg.textContent = d.message || 'Role saved'; location.reload(); }});
          }};
          refreshSessions(); refreshLogs();
          setInterval(refreshSessions, 30000);
        }})();
        </script>
        """
        return layout("Server Control", body, "admin")

    @app.route("/api/admin/server/status")
    @login_required("view_admin")
    def api_admin_server_status():
        return jsonify(server_control.get_status(base_dir))

    @app.route("/api/admin/server/start", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_start():
        force = bool((request.get_json(silent=True) or {}).get("force"))
        return jsonify(server_control.start_server(base_dir, force=force))

    @app.route("/api/admin/server/stop", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_stop():
        return jsonify(server_control.stop_server())

    @app.route("/api/admin/server/restart", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_restart():
        return jsonify(server_control.restart_server(base_dir))

    @app.route("/api/admin/server/repair-database", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_repair_database():
        return jsonify(server_control.repair_database_lock(base_dir))

    @app.route("/api/admin/server/sessions")
    @login_required("view_admin")
    def api_admin_server_sessions():
        sessions = server_control.get_sessions(base_dir)
        return jsonify({"ok": True, "sessions": sessions, "count": len(sessions)})

    @app.route("/api/admin/server/logs")
    @login_required("view_admin")
    def api_admin_server_logs():
        tail = int(request.args.get("tail", 100))
        return jsonify({"ok": True, "text": server_control.tail_logs(tail)})

    @app.route("/api/admin/server/firewall", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_firewall():
        return jsonify(server_control.allow_firewall())

    @app.route("/api/admin/server/power-24x7", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_power_24x7():
        return jsonify(server_control.apply_power_24x7())

    @app.route("/api/admin/server/reboot-host", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_reboot_host():
        payload = request.get_json(silent=True) or {}
        delay = int(payload.get("delay_seconds", 60))
        return jsonify(server_control.reboot_host_pc(delay))

    @app.route("/api/admin/server/shutdown-host", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_shutdown_host():
        payload = request.get_json(silent=True) or {}
        delay = int(payload.get("delay_seconds", 45))
        return jsonify(server_control.shutdown_host_pc(delay))

    @app.route("/api/admin/server/role", methods=["POST"])
    @login_required("view_admin")
    def api_admin_server_role():
        payload = request.get_json(silent=True) or {}
        pc_role = str(payload.get("pc_role") or PC_ROLE_OWNER_OFFICE)
        host_strategy = str(payload.get("host_strategy") or STRATEGY_LOCAL_EMBEDDED)
        reg = confirm_pc_role(pc_role, host_strategy, base_dir)
        return jsonify({"ok": True, "message": f"PC role saved: {pc_role}", "registry": reg})

    @app.route("/api/admin/inbox")
    @login_required("view_admin")
    def api_admin_inbox():
        from app.admin_inbox import aggregate_inbox

        return jsonify(aggregate_inbox(base_dir))
