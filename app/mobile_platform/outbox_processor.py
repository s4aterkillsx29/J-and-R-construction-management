# -*- coding: utf-8 -*-
"""Upload pending mobile outbox items to dropbox-records when host online."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def process_pending(conn, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    from app.dropbox_workspace import resolve_dropbox_records

    base = base_dir or Path(__file__).resolve().parents[2]
    dropbox = resolve_dropbox_records(base)
    report: Dict[str, Any] = {"ok": True, "processed": 0, "errors": []}
    if not dropbox:
        report["ok"] = False
        report["errors"].append("dropbox-records not found")
        return report

    rows = conn.execute(
        "SELECT * FROM mobile_outbox WHERE status='pending' ORDER BY id LIMIT 20"
    ).fetchall()
    for row in rows:
        oid = row["id"]
        event_type = row["event_type"]
        job_code = row["job_code"] or "UNASSIGNED"
        try:
            if event_type in {"photo", "receipt", "file"}:
                files = conn.execute(
                    "SELECT * FROM mobile_outbox_files WHERE outbox_id=?", (oid,)
                ).fetchall()
                job_slug = job_code.replace("JRC-", "JRC-")
                dest_base = dropbox / "01_Jobs" / job_slug / "04_Photos"
                dest_base.mkdir(parents=True, exist_ok=True)
                for f in files:
                    src = Path(f["temp_path"])
                    if src.is_file():
                        dest = dest_base / f["filename"]
                        shutil.copy2(src, dest)
                        conn.execute(
                            "UPDATE mobile_outbox_files SET uploaded=1, dropbox_path=? WHERE id=?",
                            (str(dest), f["id"]),
                        )
            elif event_type == "note":
                payload = json.loads(row["payload_json"] or "{}")
                note = payload.get("note", "")
                log_dir = dropbox / "01_Jobs" / job_code
                if log_dir.is_dir():
                    log_file = log_dir / f"mobile_note_{datetime.now():%Y%m%d_%H%M%S}.txt"
                    log_file.write_text(note, encoding="utf-8")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE mobile_outbox SET status='done', processed_at=? WHERE id=?",
                (now, oid),
            )
            conn.commit()
            report["processed"] += 1
        except Exception as exc:
            conn.execute(
                "UPDATE mobile_outbox SET status='error', error_text=? WHERE id=?",
                (str(exc)[:500], oid),
            )
            conn.commit()
            report["errors"].append(str(exc))
    if report["errors"]:
        report["ok"] = len(report["errors"]) < len(rows)
    return report
