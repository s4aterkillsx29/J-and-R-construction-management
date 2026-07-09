"""Admin routes: remote host PC control from anywhere (Tailscale + RustDesk + RDP)."""
from __future__ import annotations

import html
import json
from typing import Callable

from flask import flash, jsonify, redirect, request, url_for

from app.remote_pc_control import (
    build_remote_pc_status,
    is_office_server_pc,
    launch_office_connect,
    launch_rdp,
    launch_rustdesk,
    read_host_mac,
    run_backdoor_verification,
    run_host_power_api,
    run_office_host_command,
    save_remote_pc_settings,
    send_wake_on_lan,
)


def register_remote_pc_routes(
    app,
    *,
    login_required,
    layout,
    get_app_setting,
    set_app_setting,
    now_iso: Callable[[], str],
    log_event: Callable[..., None],
) -> None:

    def _office_action_guard() -> bool:
        if is_office_server_pc():
            return True
        flash(
            "OS launch actions run on the office PC where JRC server is started (JRConst). "
            "Admins can still use URLs and RustDesk ID below from any device.",
            "warning",
        )
        return False

    def _run_office_host_command(command: str) -> tuple[bool, str]:
        return run_office_host_command(command)

    def _run_host_power_api(host_ip: str, action: str) -> tuple[bool, str]:
        return run_host_power_api(host_ip, action)

    @app.route("/admin/remote-pc", methods=["GET", "POST"])
    @login_required("view_admin")
    def admin_remote_pc():
        if request.method == "POST":
            action = request.form.get("action", "save")
            ip = request.form.get("remote_host_lan_ip", "").strip() or None
            ts_ip = request.form.get("remote_host_tailscale_ip", "").strip()

            if action == "verify_backdoors":
                vr = run_backdoor_verification(get_app_setting)
                set_app_setting("remote_pc_last_verify_at", now_iso())
                set_app_setting("remote_pc_last_verify_json", json.dumps(vr)[:12000])
                log_event("Remote PC", f"Backdoor verify: {vr.get('passed')}/{vr.get('total')} PASS")
                flash(
                    f"Backdoor verification: {vr.get('passed')}/{vr.get('total')} checks passed.",
                    "success" if vr.get("all_ok") else "warning",
                )
                return redirect(url_for("admin_remote_pc"))

            if action == "probe":
                st = build_remote_pc_status(get_app_setting)
                set_app_setting("remote_pc_last_probe_at", now_iso())
                set_app_setting("remote_pc_last_probe_json", json.dumps(st)[:8000])
                log_event("Remote PC", "Probe completed from admin panel")
                flash("Host probe completed.", "success")
                return redirect(url_for("admin_remote_pc"))

            if action == "launch_connect":
                if _office_action_guard():
                    ok, msg = launch_office_connect(ip or "")
                    flash(msg, "success" if ok else "error")
                return redirect(url_for("admin_remote_pc"))

            if action == "launch_rdp":
                if _office_action_guard():
                    target = ts_ip if request.form.get("use_tailscale") == "1" and ts_ip else (ip or "")
                    ok, msg = launch_rdp(target)
                    flash(msg, "success" if ok else "error")
                return redirect(url_for("admin_remote_pc"))

            if action == "launch_rustdesk":
                if _office_action_guard():
                    ok, msg = launch_rustdesk()
                    flash(msg, "success" if ok else "error")
                return redirect(url_for("admin_remote_pc"))

            if action == "wake_wol":
                if _office_action_guard():
                    mac = request.form.get("remote_host_mac", "").strip() or read_host_mac()
                    ok, msg = send_wake_on_lan(mac, ip or "")
                    log_event("Remote PC", f"Wake-on-LAN: {msg[:120]}")
                    flash(msg[:500], "success" if ok else "warning")
                return redirect(url_for("admin_remote_pc"))

            if action == "queue_reboot":
                if _office_action_guard():
                    ok, msg = _run_office_host_command("reboot")
                    flash(msg[:500], "success" if ok else "warning")
                return redirect(url_for("admin_remote_pc"))

            if action == "queue_shutdown":
                if _office_action_guard():
                    ok, msg = _run_office_host_command("shutdown")
                    flash(msg[:500], "success" if ok else "warning")
                return redirect(url_for("admin_remote_pc"))

            if action == "host_reboot_api":
                if _office_action_guard():
                    ok, msg = _run_host_power_api(ts_ip or ip or "", "reboot")
                    flash(msg[:500], "success" if ok else "warning")
                return redirect(url_for("admin_remote_pc"))

            if action == "host_shutdown_api":
                if _office_action_guard():
                    ok, msg = _run_host_power_api(ts_ip or ip or "", "shutdown")
                    flash(msg[:500], "success" if ok else "warning")
                return redirect(url_for("admin_remote_pc"))

            updates = {
                "remote_host_lan_ip": request.form.get("remote_host_lan_ip", ""),
                "remote_host_tailscale_ip": request.form.get("remote_host_tailscale_ip", ""),
                "remote_host_tailscale_name": request.form.get("remote_host_tailscale_name", ""),
                "remote_host_rustdesk_id": request.form.get("remote_host_rustdesk_id", ""),
                "remote_host_pc_name": request.form.get("remote_host_pc_name", ""),
                "remote_host_mac": request.form.get("remote_host_mac", ""),
            }
            save_remote_pc_settings(updates, set_app_setting)
            log_event("Remote PC", "Remote host PC settings updated")
            flash("Remote host PC settings saved.", "success")
            return redirect(url_for("admin_remote_pc"))

        st = build_remote_pc_status(get_app_setting)
        s = st["settings"]
        ts = st["tailscale"]
        rec = st["recommended"]
        mac = s.get("remote_host_mac") or read_host_mac()
        ts_ip = s.get("remote_host_tailscale_ip") or ts.get("self_ip") or ""
        rd_id = html.escape(s.get("remote_host_rustdesk_id") or "")

        last_verify = get_app_setting("remote_pc_last_verify_json", "")
        verify_rows = ""
        verify_summary = "Not run yet — click Verify all backdoors"
        if last_verify:
            try:
                vr = json.loads(last_verify)
                verify_summary = f"{vr.get('passed', 0)}/{vr.get('total', 0)} PASS at {html.escape(vr.get('verified_at', ''))}"
                for c in vr.get("checks", [])[:20]:
                    badge = "ok" if c.get("ok") else "red"
                    verify_rows += (
                        f"<tr><td>{html.escape(c.get('name', ''))}</td>"
                        f"<td><span class='badge {badge}'>{'PASS' if c.get('ok') else 'FAIL'}</span></td>"
                        f"<td class='muted'>{html.escape(str(c.get('detail', ''))[:80])}</td></tr>"
                    )
            except Exception:
                verify_rows = "<tr><td colspan='3'>Could not parse last verify JSON</td></tr>"

        def port_rows(probe: dict) -> str:
            rows = []
            for port, info in (probe.get("ports") or {}).items():
                badge = "ok" if info.get("open") else "red"
                rows.append(
                    f"<tr><td>{html.escape(info.get('label', port))}</td>"
                    f"<td>{html.escape(port)}</td>"
                    f"<td><span class='badge {badge}'>{'OPEN' if info.get('open') else 'closed'}</span></td></tr>"
                )
            return "".join(rows) or "<tr><td colspan='3'>No probe data</td></tr>"

        ts_badge = "ok" if ts.get("online") else ("yellow" if ts.get("installed") else "red")
        jrc_lan_badge = "ok" if st["jrc_lan"]["ok"] else "red"
        jrc_ts_badge = "ok" if st["jrc_tailscale"]["ok"] else "yellow"
        office_badge = "ok" if is_office_server_pc() else "yellow"
        rdp_ts = f"mstsc /v:{html.escape(ts_ip)}" if ts_ip else "Set Tailscale IP first"

        body = f"""
        <div class="card"><h2>Remote Host PC — Admin Full Access</h2>
          <p>All <b>admins</b> can view status, save host settings, and use connect URLs. 
          Launch buttons (RDP, RustDesk, WOL) run on the PC where the JRC server is started (office JRConst).</p>
          <p class="muted">Power recovery: sleep off · WOL · BIOS AC power on · Tailscale + RustDesk for internet.</p>
        </div>
        <div class="grid">
          <div class="stat">Office server<span class="badge {office_badge}">{'JRConst' if office_badge=='ok' else 'Remote session'}</span></div>
          <div class="stat">Tailscale<span class="badge {ts_badge}">{'Online' if ts.get('online') else ('Installed' if ts.get('installed') else 'Setup')}</span>
            <span class="muted"><code>{html.escape(ts.get('self_ip') or '—')}</code></span></div>
          <div class="stat">JRC LAN<span class="badge {jrc_lan_badge}">{'UP' if st['jrc_lan']['ok'] else 'Down'}</span></div>
          <div class="stat">JRC Tailscale<span class="badge {jrc_ts_badge}">{'UP' if st['jrc_tailscale']['ok'] else 'Down'}</span></div>
        </div>
        <div class="card"><h2>Admin connect — use from any device</h2>
          <table>
            <tr><th>Method</th><th>Same Wi-Fi (LAN)</th><th>Internet (Tailscale)</th></tr>
            <tr><td>Full PC — RustDesk</td><td colspan="2">ID: <code>{rd_id or 'save below'}</code></td></tr>
            <tr><td>Full PC — RDP</td><td><code>{html.escape(rec['lan_full_pc'])}</code></td><td><code>{html.escape(rdp_ts)}</code></td></tr>
            <tr><td>JRC app browser</td><td><a href="{html.escape(rec['lan_app'])}" target="_blank">{html.escape(rec['lan_app'])}</a></td>
                <td><a href="{html.escape(rec['app_internet'])}" target="_blank">{html.escape(rec['app_internet'])}</a></td></tr>
            <tr><td>Wake host (LAN)</td><td colspan="2">MAC <code>{html.escape(mac)}</code> — office only</td></tr>
          </table>
        </div>
        <div class="card"><h2>Launch from office server (admin)</h2>
          <form method="post" style="display:inline"><input type="hidden" name="action" value="launch_rustdesk"><button type="submit">Open RustDesk</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="launch_rdp"><input type="hidden" name="remote_host_lan_ip" value="{html.escape(s.get('remote_host_lan_ip',''))}"><button type="submit">Open RDP (LAN)</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="launch_rdp"><input type="hidden" name="use_tailscale" value="1"><input type="hidden" name="remote_host_tailscale_ip" value="{html.escape(ts_ip)}"><input type="hidden" name="remote_host_lan_ip" value="{html.escape(s.get('remote_host_lan_ip',''))}"><button type="submit" class="btn btn2">Open RDP (Tailscale)</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="launch_connect"><input type="hidden" name="remote_host_lan_ip" value="{html.escape(s.get('remote_host_lan_ip',''))}"><button type="submit" class="btn btn2">Smart Connect</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="wake_wol"><input type="hidden" name="remote_host_mac" value="{html.escape(mac)}"><input type="hidden" name="remote_host_lan_ip" value="{html.escape(s.get('remote_host_lan_ip',''))}"><button type="submit" class="btn btn2">Wake-on-LAN</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="probe"><button type="submit" class="btn btn2">Probe ports</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="verify_backdoors"><button type="submit" class="btn">Verify all backdoors</button></form>
        </div>
        <div class="card"><h2>Host power (office server)</h2>
          <p class="muted">Shutdown/reboot tries JRC API first, then office command queue. Host needs FIX_HOST_REMOTE_PATHS.bat run once.</p>
          <form method="post" style="display:inline"><input type="hidden" name="action" value="host_shutdown_api"><input type="hidden" name="remote_host_tailscale_ip" value="{html.escape(ts_ip)}"><input type="hidden" name="remote_host_lan_ip" value="{html.escape(s.get('remote_host_lan_ip',''))}"><button type="submit" class="btn warn">Shutdown host (API)</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="host_reboot_api"><input type="hidden" name="remote_host_tailscale_ip" value="{html.escape(ts_ip)}"><input type="hidden" name="remote_host_lan_ip" value="{html.escape(s.get('remote_host_lan_ip',''))}"><button type="submit" class="btn btn2">Reboot host (API)</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="queue_shutdown"><button type="submit" class="btn btn2">Queue shutdown (share)</button></form>
          <form method="post" style="display:inline;margin-left:6px"><input type="hidden" name="action" value="queue_reboot"><button type="submit" class="btn btn2">Queue reboot (share)</button></form>
        </div>
        <div class="card"><h2>Backdoor verification — {verify_summary}</h2>
          <table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>{verify_rows or "<tr><td colspan='3'>Click Verify all backdoors</td></tr>"}</table>
        </div>
        <div class="card"><h2>Host settings</h2>
          <form method="post">
            <input type="hidden" name="action" value="save">
            <label>Host PC name</label><input name="remote_host_pc_name" value="{html.escape(s.get('remote_host_pc_name', ''))}">
            <label>LAN IP</label><input name="remote_host_lan_ip" value="{html.escape(s.get('remote_host_lan_ip', ''))}">
            <label>Tailscale IP</label><input name="remote_host_tailscale_ip" value="{html.escape(s.get('remote_host_tailscale_ip', ''))}">
            <label>Tailscale DNS</label><input name="remote_host_tailscale_name" value="{html.escape(s.get('remote_host_tailscale_name', ''))}">
            <label>RustDesk ID</label><input name="remote_host_rustdesk_id" value="{rd_id}">
            <label>Host MAC (WOL)</label><input name="remote_host_mac" value="{html.escape(mac)}">
            <button type="submit">Save settings</button>
          </form>
        </div>
        <div class="card"><h2>LAN port probe — {html.escape(st['lan_probe'].get('host', ''))}</h2>
          <table><tr><th>Service</th><th>Port</th><th>Status</th></tr>{port_rows(st['lan_probe'])}</table>
        </div>
        """
        return layout("Remote Host PC", body, "admin")

    @app.route("/api/admin/remote-pc/status")
    @login_required("view_admin")
    def api_admin_remote_pc_status():
        return jsonify(build_remote_pc_status(get_app_setting))

    @app.route("/api/admin/remote-pc/verify")
    @login_required("view_admin")
    def api_admin_remote_pc_verify():
        vr = run_backdoor_verification(get_app_setting)
        set_app_setting("remote_pc_last_verify_at", now_iso())
        set_app_setting("remote_pc_last_verify_json", json.dumps(vr)[:12000])
        return jsonify(vr)
