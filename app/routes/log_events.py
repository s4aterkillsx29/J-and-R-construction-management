# -*- coding: utf-8 -*-
"""Log Event wizard — payment, helper, receipt, draw, status."""
from __future__ import annotations

import html
from typing import Callable

from flask import flash, redirect, request, url_for


def register_log_event_routes(
    app,
    *,
    login_required: Callable,
    layout: Callable,
    base_dir,
) -> None:
    EVENT_TYPES = (
        ("payment", "Customer payment / deposit"),
        ("helper", "Helper pay"),
        ("receipt", "Materials receipt"),
        ("draw", "Owner draw / labor"),
        ("status", "Job status change"),
    )

    @app.route("/log-event", methods=["GET", "POST"])
    @login_required("manage_jobs")
    def log_event_wizard():
        if request.method == "POST":
            event_type = request.form.get("event_type", "")
            job_code = request.form.get("job_code", "").strip()
            amount = request.form.get("amount", "").strip()
            note = request.form.get("note", "").strip()
            flash(
                f"Log Event queued: {event_type} JRC job {job_code} amount {amount}. "
                "Use Office Records Sync or Office AI approval to merge CSVs.",
                "success",
            )
            return redirect(url_for("log_event_wizard"))
        opts = "".join(
            f'<option value="{k}">{html.escape(l)}</option>' for k, l in EVENT_TYPES
        )
        body = f"""
        <div class="card"><h2>Log Event</h2>
        <p class="muted">One screen for field/office logging. CSV merge requires approval.</p>
        <form method="post">
          <p><label>Event type</label><select name="event_type">{opts}</select></p>
          <p><label>Job code</label><input name="job_code" placeholder="JRC-403"></p>
          <p><label>Amount (if money)</label><input name="amount" placeholder="0.00"></p>
          <p><label>Notes</label><textarea name="note" rows="4"></textarea></p>
          <button type="submit">Save to program queue</button>
        </form>
        <p><a class="btn btn2" href="/office-ai/approvals">Pending approvals</a></p></div>
        """
        return layout("Log Event", body, "business")
