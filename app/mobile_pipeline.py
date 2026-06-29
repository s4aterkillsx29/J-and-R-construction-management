"""Mobile job pipeline board — kanban stages for phone dashboard."""
from __future__ import annotations

import html
import sqlite3
from typing import Any, Dict, List

PIPELINE_STAGES = [
    ("Lead", "New leads and inquiries"),
    ("Estimate Sent", "Quotes waiting on customer"),
    ("Approved", "Approved — not started"),
    ("Active", "Work in progress"),
    ("Waiting Payment", "Job done — awaiting payment"),
    ("Closed Paid", "Completed and paid"),
    ("Closed Unpaid", "Closed — balance due"),
]

STAGE_ALIASES = {
    "lead": "Lead",
    "estimate sent": "Estimate Sent",
    "quote sent": "Estimate Sent",
    "approved": "Approved",
    "active": "Active",
    "in progress": "Active",
    "waiting payment": "Waiting Payment",
    "closed paid": "Closed Paid",
    "closed unpaid": "Closed Unpaid",
}


def normalize_stage(status: str) -> str:
    s = (status or "Lead").strip()
    key = s.lower()
    return STAGE_ALIASES.get(key, s if s in [x[0] for x in PIPELINE_STAGES] else "Lead")


def pipeline_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    counts = {name: 0 for name, _ in PIPELINE_STAGES}
    for row in conn.execute("SELECT status FROM jobs").fetchall():
        stage = normalize_stage(row["status"] or "Lead")
        if stage not in counts:
            counts[stage] = 0
        counts[stage] += 1
    return counts


def pipeline_jobs_by_stage(conn: sqlite3.Connection, view_money: bool = False) -> Dict[str, List[sqlite3.Row]]:
    buckets: Dict[str, List[sqlite3.Row]] = {name: [] for name, _ in PIPELINE_STAGES}
    rows = conn.execute(
        "SELECT id, job_name, status, price, paid, address, updated_at FROM jobs ORDER BY updated_at DESC"
    ).fetchall()
    for row in rows:
        stage = normalize_stage(row["status"] or "Lead")
        if stage not in buckets:
            buckets[stage] = []
        buckets[stage].append(row)
    return buckets


def render_mobile_pipeline_html(conn: sqlite3.Connection, view_money: bool, money_fn) -> str:
    counts = pipeline_counts(conn)
    buckets = pipeline_jobs_by_stage(conn, view_money)
    summary = "".join(
        f"<div class='stat'><span class='muted'>{html.escape(name)}</span><b>{counts.get(name, 0)}</b></div>"
        for name, _ in PIPELINE_STAGES
    )
    columns = []
    for name, desc in PIPELINE_STAGES:
        jobs = buckets.get(name, [])[:12]
        cards = ""
        for j in jobs:
            money_line = f"<span class='muted'>{money_fn(j['paid'])} / {money_fn(j['price'])}</span>" if view_money else ""
            cards += (
                f"<a class='pipeline-card' href='/mobile/job/{j['id']}'>"
                f"<b>{html.escape(j['job_name'] or 'Job')}</b><br>"
                f"<span class='muted'>{html.escape((j['address'] or '')[:40])}</span><br>{money_line}</a>"
            )
        if not cards:
            cards = "<p class='muted'>None</p>"
        columns.append(
            f"<div class='pipeline-col'><h3>{html.escape(name)}</h3>"
            f"<p class='muted'>{html.escape(desc)}</p>{cards}</div>"
        )
    css = """
    <style>
    .pipeline-board{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;overflow-x:auto}
    .pipeline-col{background:rgba(17,17,17,.9);border:1px solid rgba(132,204,22,.25);border-radius:14px;padding:12px;min-height:120px}
    .pipeline-col h3{margin:0 0 4px;color:#a3e635;font-size:13px}
    .pipeline-card{display:block;background:rgba(132,204,22,.08);border:1px solid rgba(132,204,22,.2);
    border-radius:10px;padding:10px;margin:8px 0;color:#f5f5f5;text-decoration:none;font-size:13px}
  .pipeline-card:hover{border-color:#84cc16;background:rgba(132,204,22,.15)}
    </style>
    """
    return (
        css
        + f"<div class='grid'>{summary}</div>"
        + "<div class='card'><h2>Job Pipeline Board</h2>"
        + "<p class='muted'>Live job stages — tap a card for details. Updated from your database on each load.</p>"
        + f"<div class='pipeline-board'>{''.join(columns)}</div></div>"
    )


def pipeline_api_payload(conn: sqlite3.Connection) -> Dict[str, Any]:
    buckets = pipeline_jobs_by_stage(conn)
    return {
        "stages": [{"name": n, "description": d, "count": len(buckets.get(n, []))} for n, d in PIPELINE_STAGES],
        "jobs": {
            stage: [dict(r) for r in rows[:20]]
            for stage, rows in buckets.items()
        },
        "counts": pipeline_counts(conn),
    }
