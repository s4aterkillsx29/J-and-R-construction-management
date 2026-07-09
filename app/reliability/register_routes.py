# -*- coding: utf-8 -*-
"""Flask /admin/reliability + API for Guardian control."""
from __future__ import annotations

import html
from typing import Callable

from flask import flash, jsonify, redirect, request, url_for

from app.reliability import guardian_store
from app.reliability.consistency_audit import format_report, run_read_only_audit
from app.reliability.guardian_report import save_report
from app.reliability.guardian_scheduler import get_scheduler


def register_reliability_routes(
    app,
    *,
    login_required: Callable,
    layout: Callable,
    base_dir,
) -> None:
    @app.route("/admin/reliability", methods=["GET", "POST"])
    @login_required("view_admin")
    def admin_reliability_page():
        conn = guardian_store.connect()
        try:
            if request.method == "POST":
                action = request.form.get("action", "")
                if action == "save_settings":
                    for key in ("enabled", "profile", "auto_repair"):
                        val = request.form.get(key, "")
                        if val:
                            guardian_store.set_setting(conn, key, val)
                    flash("Guardian settings saved.", "success")
                elif action == "run_now":
                    prof = request.form.get("profile_run", "light")
                    sched = get_scheduler(base_dir)
                    result = sched.run_now(prof)
                    save_report(
                        base_dir,
                        "RunNow",
                        str(result),
                    )
                    flash(f"Guardian {prof} run complete.", "success")
                elif action == "consistency_audit":
                    rep = run_read_only_audit(base_dir)
                    save_report(base_dir, "ConsistencyAudit", format_report(rep))
                    flash("Consistency audit saved to exports.", "success")
                return redirect(url_for("admin_reliability_page"))

            settings = {
                k: guardian_store.get_setting(conn, k, "")
                for k in ("enabled", "profile", "auto_repair", "paused_until")
            }
            events = guardian_store.recent_events(conn, 25)
            status = guardian_store.latest_status(conn)
        finally:
            conn.close()

        ev_rows = ""
        for e in events:
            ev_rows += (
                f"<tr><td>{html.escape(str(e.get('event_time','')))}</td>"
                f"<td>{html.escape(str(e.get('level','')))}</td>"
                f"<td>{html.escape(str(e.get('component','')))}</td>"
                f"<td>{html.escape(str(e.get('message','')))[:120]}</td></tr>"
            )
        body = f"""
        <div class="card"><h2>Reliability Guardian</h2>
        <p>Status chip: <b>{html.escape(status)}</b></p>
        <form method="post">
          <input type="hidden" name="action" value="save_settings">
          <p><label>Enabled</label>
            <select name="enabled"><option value="1" {'selected' if settings.get('enabled')=='1' else ''}>On</option>
            <option value="0" {'selected' if settings.get('enabled')=='0' else ''}>Off</option></select></p>
          <p><label>Profile</label>
            <select name="profile">
              {''.join(f'<option value="{p}" {"selected" if settings.get("profile")==p else ""}>{p.title()}</option>' for p in ("off","light","normal","full"))}
            </select></p>
          <p><label>Auto-repair safe items</label>
            <select name="auto_repair"><option value="1" {'selected' if settings.get('auto_repair')=='1' else ''}>Yes</option>
            <option value="0" {'selected' if settings.get('auto_repair')=='0' else ''}>No</option></select></p>
          <button type="submit">Save Settings</button>
        </form>
        </div>
        <div class="card"><h2>Actions</h2>
        <form method="post" style="display:inline"><input type="hidden" name="action" value="run_now">
          <select name="profile_run"><option value="light">Light</option><option value="normal">Normal</option><option value="full">Full</option></select>
          <button type="submit">Run Now</button></form>
        <form method="post" style="display:inline;margin-left:8px"><input type="hidden" name="action" value="consistency_audit">
          <button type="submit">Consistency Audit (read-only)</button></form>
        <p><a class="btn btn2" href="/admin/troubleshooter">Full Troubleshooter</a>
        <a class="btn btn2" href="/office-ai/approvals">Pending AI Approvals</a></p></div>
        <div class="card"><h2>Recent Events</h2>
        <table><tr><th>Time</th><th>Level</th><th>Component</th><th>Message</th></tr>{ev_rows or '<tr><td colspan=4>No events yet</td></tr>'}</table></div>
        """
        return layout("Reliability Guardian", body, "admin")

    @app.route("/api/guardian/status")
    @login_required("view_admin")
    def api_guardian_status():
        conn = guardian_store.connect()
        try:
            return jsonify(
                {
                    "status": guardian_store.latest_status(conn),
                    "profile": guardian_store.get_setting(conn, "profile", "light"),
                    "enabled": guardian_store.get_setting(conn, "enabled", "1"),
                }
            )
        finally:
            conn.close()

    @app.route("/admin/ai-viability", methods=["GET"])
    @login_required("view_admin")
    def admin_ai_viability_page():
        import json
        from pathlib import Path

        matrix_path = Path(__file__).resolve().parents[1] / "office_ai" / "ai_viability_matrix.json"
        text = matrix_path.read_text(encoding="utf-8") if matrix_path.is_file() else "{}"
        try:
            data = json.loads(text)
            pretty = html.escape(json.dumps(data, indent=2))
        except Exception:
            pretty = html.escape(text)
        body = f"<div class='card'><h2>AI Viability Matrix</h2><pre>{pretty}</pre></div>"
        return layout("AI Viability", body, "admin")
