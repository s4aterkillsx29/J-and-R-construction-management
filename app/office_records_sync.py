# -*- coding: utf-8 -*-
"""Sync JRC Construction Manager with dropbox-records office files (Phases 1-2)."""
from __future__ import annotations

import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

OFFICE_RATES = {
    "owner_hourly_rate": "30",
    "owner_daily_rate": "240",
    "owner_office_daily_rate": "170",
    "helper_daily_rate": "140",
    "helper_overhead_per_work": "50",
    "dump_trip_fee_rule": "Actual dump fee plus $50 J&R trip fee",
    "family_discount_note": "Family/friends jobs: customer price on invoice; margin internal only",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_dropbox_records(base_dir: Path) -> Optional[Path]:
    """Locate dropbox-records folder from install, Cursor office project, or cloud mirror."""
    from app.dropbox_workspace import resolve_dropbox_records

    return resolve_dropbox_records(base_dir)


def apply_office_business_standards(conn: sqlite3.Connection) -> List[str]:
    """Phase 0/standards — push office rate rules into app_settings."""
    notes: List[str] = []
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    extras = [
        ("std_owner_hourly_rate", "Owner labor rate ($/hr)", OFFICE_RATES["owner_hourly_rate"]),
        ("std_owner_daily_rate", "Owner labor rate ($/8-hr day)", OFFICE_RATES["owner_daily_rate"]),
        ("std_owner_office_daily_rate", "Owner office day pay ($/full day)", OFFICE_RATES["owner_office_daily_rate"]),
        ("std_owner_draw_account", "Default paid-from account", "Business checking"),
        ("std_owner_draw_work_type", "Default owner draw work type", "Business office full day"),
        (
            "std_owner_draw_rule",
            "Owner draw / paid myself rule",
            "Log owner draws from business checking as equity distributions, not helper pay or deductible expenses.",
        ),
        (
            "std_log_sync_rule",
            "Log + sync rule",
            'When Jacob says "log", update Dropbox office CSVs/field logs AND run python -m app.dropbox_workspace --sync.',
        ),
        ("std_helper_daily_rate", "Helper default ($/8-hr day)", OFFICE_RATES["helper_daily_rate"]),
        (
            "std_helper_overhead_per_work",
            "Helper overhead per work instance",
            OFFICE_RATES["helper_overhead_per_work"],
        ),
        ("std_dump_trip_fee_rule", "Dump/disposal rule", OFFICE_RATES["dump_trip_fee_rule"]),
        (
            "std_office_sync_time",
            "Last office records sync",
            _now(),
        ),
    ]
    for key, _label, val in extras:
        conn.execute(
            "INSERT INTO app_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, val),
        )
        notes.append(f"standard {key}={val}")
    conn.commit()
    return notes


def _map_status(office_status: str) -> str:
    s = (office_status or "").lower()
    if "completed" in s or "paid" in s:
        return "Completed"
    if "lead" in s or "draft" in s or "estimate" in s:
        return "Lead"
    if "active" in s or "invoiced" in s:
        return "Active"
    if "dead" in s or "archived" in s:
        return "Archived"
    return "Lead"


def import_job_register(conn: sqlite3.Connection, dropbox: Path) -> Tuple[int, int, List[str]]:
    """Phase 1 — import JRC_JOB_RELATION_REGISTER.csv into jobs + customers."""
    from app.schema_migrations import ensure_all_shared_schemas

    ensure_all_shared_schemas(conn)
    reg = dropbox / "08_Admin_Standards" / "JRC_JOB_RELATION_REGISTER.csv"
    if not reg.is_file():
        return 0, 0, [f"Missing register: {reg}"]

    notes: List[str] = []
    inserted = updated = 0
    with reg.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = (row.get("Job_Code") or "").strip()
            if not code or code in ("JRC-ADM", "JRC-GEN"):
                continue
            customer = (row.get("Customer") or "TBD").strip()
            address = (row.get("Address") or "").strip()
            status = _map_status(row.get("Status") or "")
            folder = (row.get("New_Target_Subfolder") or "").strip()
            job_name = f"{code} — {customer}" if customer else code
            office_status = (row.get("Status") or "").strip()

            cur = conn.execute(
                "SELECT id FROM customers WHERE name=? LIMIT 1", (customer,)
            ).fetchone()
            if cur:
                cid = int(cur[0])
            else:
                conn.execute(
                    "INSERT INTO customers(name,address,notes,created_at) VALUES(?,?,?,?)",
                    (customer, address, f"Office register {code}", _now()),
                )
                cid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            existing = conn.execute(
                "SELECT id FROM jobs WHERE job_code=? LIMIT 1", (code,)
            ).fetchone()
            if existing:
                jid = int(existing[0])
                conn.execute(
                    """
                    UPDATE jobs SET
                        customer_id=?, job_name=?, job_address=?, address=?,
                        status=?, office_folder_path=?, office_status=?,
                        notes=COALESCE(notes,'') || ?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        cid,
                        job_name,
                        address,
                        address,
                        status,
                        folder,
                        office_status,
                        "",
                        _now(),
                        jid,
                    ),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        customer_id, job_name, job_address, address, status, scope,
                        contract_price, price, job_code, office_folder_path, office_status,
                        notes, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,0,0,?,?,?,?,?,?)
                    """,
                    (
                        cid,
                        job_name,
                        address,
                        address,
                        status,
                        (row.get("Notes") or "")[:500],
                        code,
                        folder,
                        office_status,
                        f"Imported from office register {_now()}",
                        _now(),
                        _now(),
                    ),
                )
                inserted += 1
    conn.commit()
    notes.append(f"jobs inserted={inserted} updated={updated}")
    return inserted, updated, notes


def register_dropbox_file_source(conn: sqlite3.Connection, dropbox: Path) -> None:
    from app.schema_migrations import ensure_unified_file_sources_schema

    ensure_unified_file_sources_schema(conn)
    path = str(dropbox.resolve())
    row = conn.execute(
        "SELECT id FROM file_sources WHERE folder_path=? OR root_path=? LIMIT 1",
        (path, path),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE file_sources SET active=1, enabled=1, label=?, source_name=? WHERE id=?",
            ("dropbox-records (office)", "dropbox-records", int(row[0])),
        )
    else:
        conn.execute(
            """
            INSERT INTO file_sources (
                label, source_name, source_type, folder_path, root_path,
                active, enabled, notes, created_at
            ) VALUES (?,?,?,?,?,1,1,?,?)
            """,
            (
                "dropbox-records (office)",
                "dropbox-records",
                "dropbox_office",
                path,
                path,
                "JRC office source of truth — Cursor assistant",
                _now(),
            ),
        )
    conn.commit()


def export_worker_payments_csv(conn: sqlite3.Connection, out_path: Path) -> int:
    """Phase 2 — export worker_payments in office Payroll_Helper_Register format."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(worker_payments)")}
    date_parts = [f"wp.{c}" for c in ("date", "work_date", "paid_at", "created_at") if c in cols]
    date_expr = "COALESCE(" + ", ".join(date_parts) + ", '')" if date_parts else "''"
    desc_parts = [f"wp.{c}" for c in ("work_description", "description") if c in cols]
    desc_expr = "COALESCE(" + ", ".join(desc_parts) + ", '')" if desc_parts else "''"
    notes_expr = "wp.notes" if "notes" in cols else "''"
    method_expr = "wp.payment_method" if "payment_method" in cols else "''"
    sql = f"""
        SELECT w.name, j.job_name, wp.amount, {date_expr}, {method_expr}, {desc_expr}, {notes_expr}
        FROM worker_payments wp
        LEFT JOIN workers w ON w.id = wp.worker_id
        LEFT JOIN jobs j ON j.id = wp.job_id
        WHERE COALESCE(wp.source, '') != 'Office CSV'
          AND COALESCE({notes_expr}, '') NOT LIKE '%[office import]%'
        ORDER BY wp.id DESC
    """
    rows = conn.execute(sql).fetchall()
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Worker", "Job", "Amount", "Date/Timing", "Status", "Notes"])
        for name, job, amt, dt, method, desc, notes in rows:
            w.writerow(
                [
                    name or "",
                    job or "",
                    f"{float(amt or 0):.2f}",
                    dt or "",
                    "Paid",
                    " — ".join(x for x in (desc, method, notes) if x).strip(),
                ]
            )
    return len(rows)


def export_income_preview_csv(conn: sqlite3.Connection, out_path: Path) -> int:
    """Phase 2 — export job deposits/balances in office Income_Deposit format."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    jcols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    dep_col = "deposit_paid" if "deposit_paid" in jcols else "deposit"
    bal_col = "balance_paid" if "balance_paid" in jcols else "paid"
    rows = conn.execute(
        f"""
        SELECT j.job_code, j.job_name, j.{dep_col}, j.{bal_col}, j.payment_method, j.status, j.notes
        FROM jobs j
        WHERE COALESCE(j.{dep_col},0)+COALESCE(j.{bal_col},0)+COALESCE(j.paid,0) > 0
        ORDER BY j.updated_at DESC
        """
    ).fetchall()
    count = 0
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Project", "Type", "Amount", "Method", "Status", "Notes"])
        for code, name, dep, bal, method, status, notes in rows:
            if notes and "[office import]" in str(notes):
                continue
            project = f"{code or ''} {name or ''}".strip()
            for typ, amt in (("Deposit", dep), ("Final balance", bal)):
                if float(amt or 0) <= 0:
                    continue
                w.writerow(
                    [
                        _now()[:10],
                        project,
                        typ,
                        f"${float(amt):.2f}",
                        method or "",
                        status or "",
                        "Export from jr_business.db — verify before merging to office CSV",
                    ]
                )
                count += 1
    return count


def import_income_from_office_csv(conn: sqlite3.Connection, dropbox: Path) -> Tuple[int, List[str]]:
    """Phase 2 — align program job deposits from office income register."""
    path = dropbox / "04_FINANCIAL_TRACKING" / "Income_Deposits_Balances" / "Income_Deposit_Balance_Register.csv"
    notes: List[str] = []
    if not path.is_file():
        return 0, [f"Missing income register: {path}"]
    jcols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    dep_col = "deposit_paid" if "deposit_paid" in jcols else "deposit"
    bal_col = "balance_paid" if "balance_paid" in jcols else "paid"
    imported = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            project = (row.get("Project") or "").strip()
            if not project:
                continue
            amt = _normalize_amount(row.get("Amount") or "0")
            try:
                val = float(amt)
            except ValueError:
                continue
            if val <= 0:
                continue
            jid = _find_job_id(conn, project)
            if not jid:
                continue
            typ = (row.get("Type") or "").lower()
            job = conn.execute(f"SELECT id, {dep_col}, {bal_col}, notes FROM jobs WHERE id=?", (jid,)).fetchone()
            if not job:
                continue
            dep = float(job[1] or 0)
            bal = float(job[2] or 0)
            updated = False
            if "deposit" in typ and dep <= 0:
                conn.execute(
                    f"UPDATE jobs SET {dep_col}=?, notes=COALESCE(notes,'') || ?, updated_at=? WHERE id=?",
                    (val, " [office import]", _now(), jid),
                )
                updated = True
            elif ("final" in typ or "balance" in typ) and bal <= 0:
                conn.execute(
                    f"UPDATE jobs SET {bal_col}=?, notes=COALESCE(notes,'') || ?, updated_at=? WHERE id=?",
                    (val, " [office import]", _now(), jid),
                )
                updated = True
            if updated:
                imported += 1
    if imported:
        conn.commit()
    notes.append(f"income imported from office: {imported} row(s)")
    return imported, notes


def _find_worker_id(conn: sqlite3.Connection, name: str) -> Optional[int]:
    name = (name or "").strip()
    if not name:
        return None
    rows = conn.execute("SELECT id, name FROM workers ORDER BY name").fetchall()
    lower = name.lower()
    for wid, wname in rows:
        if (wname or "").strip().lower() == lower:
            return int(wid)
    for wid, wname in rows:
        wn = (wname or "").strip().lower()
        if lower in wn or wn in lower:
            return int(wid)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(workers)")}
    fields: List[str] = ["name"]
    values: List[object] = [name]
    if "w9_status" in cols:
        fields.extend(["w9_status", "default_day_rate"])
        values.extend(["Unknown", float(OFFICE_RATES["helper_daily_rate"])])
    elif "default_rate" in cols:
        fields.append("default_rate")
        values.append(float(OFFICE_RATES["helper_daily_rate"]))
    if "classification" in cols:
        fields.append("classification")
        values.append("Helper")
    if "notes" in cols:
        fields.append("notes")
        values.append("Imported from office payroll CSV")
    if "active" in cols:
        fields.append("active")
        values.append(1)
    if "created_at" in cols:
        fields.append("created_at")
        values.append(_now())
    placeholders = ",".join("?" * len(fields))
    conn.execute(
        f"INSERT INTO workers ({','.join(fields)}) VALUES ({placeholders})",
        values,
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _find_job_id(conn: sqlite3.Connection, job_label: str) -> Optional[int]:
    job_label = (job_label or "").strip()
    if not job_label:
        return None
    rows = conn.execute("SELECT id, job_name, job_code FROM jobs ORDER BY id").fetchall()
    lower = job_label.lower()
    for jid, jname, jcode in rows:
        if (jcode or "").strip().lower() and (jcode or "").strip().lower() in lower:
            return int(jid)
    for jid, jname, jcode in rows:
        jn = (jname or "").strip().lower()
        if lower in jn or jn in lower:
            return int(jid)
    return None


def _payment_key_db(conn: sqlite3.Connection, worker_id: int, job_id: Optional[int], amount: float, date_val: str) -> Tuple[str, str, str]:
    wname = conn.execute("SELECT name FROM workers WHERE id=?", (worker_id,)).fetchone()
    worker = wname[0] if wname else ""
    jname = ""
    if job_id:
        row = conn.execute("SELECT job_name FROM jobs WHERE id=?", (job_id,)).fetchone()
        jname = row[0] if row else ""
    return _payroll_fuzzy_key(worker, jname, f"{amount:.2f}", date_val)


def import_payroll_from_office_csv(conn: sqlite3.Connection, dropbox: Path) -> Tuple[int, List[str]]:
    """Phase 2 — import office Payroll_Helper_Register.csv rows missing from DB."""
    from app.schema_migrations import ensure_all_shared_schemas

    ensure_all_shared_schemas(conn)
    path = dropbox / "05_Helper_Pay_Workers" / "Payroll_Helper_Register.csv"
    notes: List[str] = []
    if not path.is_file():
        return 0, [f"Missing payroll register: {path}"]

    cols = {r[1] for r in conn.execute("PRAGMA table_info(worker_payments)")}
    date_col = "date" if "date" in cols else "work_date" if "work_date" in cols else "date"

    existing_keys = set()
    for row in conn.execute(
        f"""
        SELECT wp.worker_id, wp.job_id, wp.amount, wp.{date_col}
        FROM worker_payments wp
        """
    ).fetchall():
        existing_keys.add(_payment_key_db(conn, int(row[0]), row[1], float(row[2] or 0), str(row[3] or "")))

    imported = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            worker_name = (row.get("Worker") or "").strip()
            job_name = (row.get("Job") or "").strip()
            amount = _normalize_amount(row.get("Amount") or "0")
            try:
                amt = float(amount)
            except ValueError:
                continue
            if amt <= 0:
                continue
            date_val = (row.get("Date/Timing") or "").strip()
            status = (row.get("Status") or "Paid").strip() or "Paid"
            note_parts = [row.get("Notes") or "", "[office import]"]
            notes_text = " ".join(x for x in note_parts if x).strip()

            wid = _find_worker_id(conn, worker_name)
            jid = _find_job_id(conn, job_name)
            if wid is None:
                continue
            key = _payroll_fuzzy_key(worker_name, job_name, amount, date_val)
            if key in existing_keys:
                continue

            if date_col == "work_date":
                conn.execute(
                    f"""
                    INSERT INTO worker_payments (worker_id, job_id, work_date, amount, payment_method, status, notes, source)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (wid, jid, date_val or _now()[:10], amt, "Office CSV", status, notes_text, "Office CSV"),
                )
            elif "work_description" in cols:
                conn.execute(
                    """
                    INSERT INTO worker_payments (worker_id, job_id, date, work_description, amount, payment_method, status, notes)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (wid, jid, date_val or _now()[:10], notes_text, amt, "Office CSV", status, notes_text),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO worker_payments (worker_id, job_id, date, amount, payment_method, status, notes)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (wid, jid, date_val or _now()[:10], amt, "Office CSV", status, notes_text),
                )
            existing_keys.add(key)
            imported += 1

    if imported:
        conn.commit()
    notes.append(f"payroll imported from office: {imported} row(s)")
    return imported, notes


def _normalize_amount(val: str) -> str:
    s = (val or "").strip().replace("$", "").replace(",", "")
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return s


def _normalize_worker(name: str) -> str:
    n = (name or "").strip().lower()
    if not n:
        return ""
    if n in ("unnamed helper", "helper"):
        return "brandon"
    if n.startswith("brandon"):
        return "brandon"
    if "jackie" in n and "white" in n:
        return "jackie white"
    if "richard" in n:
        return "richard millikin"
    if "dusty" in n:
        return "dusty duncan"
    return n


def _normalize_date_key(date_val: str) -> str:
    d = (date_val or "").strip().lower()
    if not d or d == "confirmed":
        return ""
    return d[:10] if len(d) >= 10 else d


def _payroll_fuzzy_key(worker: str, job: str, amount: str, date_val: str) -> Tuple[str, str, str]:
    """Match office rows even when job labels or worker names differ slightly."""
    return (
        _normalize_worker(worker),
        _normalize_amount(amount),
        _normalize_date_key(date_val) or (job or "").strip().lower()[:40],
    )


def _payroll_key(row: Dict[str, str]) -> Tuple[str, str, str]:
    return _payroll_fuzzy_key(
        row.get("Worker") or "",
        row.get("Job") or "",
        row.get("Amount") or "",
        row.get("Date/Timing") or "",
    )


def _owner_draw_key(row: Dict[str, str]) -> Tuple[str, str, str]:
    return _draw_key(
        row.get("Date") or "",
        row.get("Amount") or "",
        row.get("Description") or row.get("Work_Type") or "",
    )


def _draw_key(draw_date: str, amount: str, description: str) -> Tuple[str, str, str]:
    return ((draw_date or "").strip()[:10], _normalize_amount(amount), (description or "").strip().lower())


def export_owner_draws_preview_csv(conn: sqlite3.Connection, out_path: Path) -> int:
    from app.owner_draws import export_owner_draws_csv

    return export_owner_draws_csv(conn, out_path)


def import_owner_draws_office(conn: sqlite3.Connection, dropbox: Path) -> Tuple[int, List[str]]:
    from app.owner_draws import import_owner_draws_from_office_csv

    return import_owner_draws_from_office_csv(conn, dropbox)


def _income_key(row: Dict[str, str]) -> Tuple[str, str, str, str]:
    return (
        (row.get("Date") or "").strip(),
        (row.get("Project") or "").strip().lower(),
        (row.get("Type") or "").strip().lower(),
        _normalize_amount(row.get("Amount") or ""),
    )


def _read_csv_dicts(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    if not path.is_file():
        return [], []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        return fields, list(reader)


def _write_csv_dicts(path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def merge_preview_into_office_csv(
    office_path: Path,
    preview_rows: List[Dict[str, str]],
    key_fn,
    backup_dir: Path,
    source_tag: str,
) -> Tuple[int, int, List[str]]:
    """Phase 2 — append preview rows into office CSV with backup and deduplication."""
    notes: List[str] = []
    fields, existing = _read_csv_dicts(office_path)
    if not fields and preview_rows:
        fields = list(preview_rows[0].keys())
    if not fields:
        notes.append(f"skip merge — no columns: {office_path.name}")
        return 0, len(existing), notes

    backup_dir.mkdir(parents=True, exist_ok=True)
    if office_path.is_file():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = backup_dir / f"{office_path.stem}_pre_merge_{stamp}{office_path.suffix}"
        try:
            backup.write_bytes(office_path.read_bytes())
            notes.append(f"backup {backup.name}")
        except OSError as exc:
            notes.append(f"backup skipped ({exc}) — merge continues")

    seen = {key_fn(row) for row in existing}
    added = 0
    for row in preview_rows:
        clean = {k: (row.get(k) or "").strip() for k in fields}
        if "Notes" in clean and source_tag:
            tag = f"[JRC Manager {source_tag}]"
            if tag not in clean["Notes"]:
                clean["Notes"] = f"{clean['Notes']} {tag}".strip()
        key = key_fn(clean)
        if key in seen:
            continue
        existing.append(clean)
        seen.add(key)
        added += 1

    _write_csv_dicts(office_path, fields, existing)
    notes.append(f"merged {added} new row(s) into {office_path.name}")
    return added, len(existing), notes


def office_csv_paths(dropbox: Path) -> Dict[str, Path]:
    return {
        "payroll": dropbox / "05_Helper_Pay_Workers" / "Payroll_Helper_Register.csv",
        "income": dropbox
        / "04_FINANCIAL_TRACKING"
        / "Income_Deposits_Balances"
        / "Income_Deposit_Balance_Register.csv",
        "owner_draws": dropbox / "06_bookkeeping" / "Owner_Draws_Register.csv",
    }


def merge_exports_to_office_records(
    dropbox: Path, exp_dir: Path, source_tag: str = "7.9.0"
) -> Dict[str, object]:
    """Phase 2 approved — merge export previews into official office CSVs."""
    paths = office_csv_paths(dropbox)
    backup_dir = dropbox / "07_JRC_MANAGER_PROGRAM_FILES" / "backups" / "office_csv"
    report: Dict[str, object] = {"notes": [], "payroll_added": 0, "income_added": 0, "owner_draws_added": 0}

    payroll_preview = exp_dir / "Payroll_Helper_Export_Preview.csv"
    _, payroll_rows = _read_csv_dicts(payroll_preview)
    if payroll_rows:
        added, total, notes = merge_preview_into_office_csv(
            paths["payroll"],
            payroll_rows,
            _payroll_key,
            backup_dir,
            source_tag,
        )
        report["payroll_added"] = added
        report["payroll_total_rows"] = total
        report["notes"].extend(notes)
    else:
        report["notes"].append("payroll preview empty — office CSV unchanged")

    income_preview = exp_dir / "Income_Deposit_Export_Preview.csv"
    _, income_rows = _read_csv_dicts(income_preview)
    if income_rows:
        added, total, notes = merge_preview_into_office_csv(
            paths["income"],
            income_rows,
            _income_key,
            backup_dir,
            source_tag,
        )
        report["income_added"] = added
        report["income_total_rows"] = total
        report["notes"].extend(notes)
    else:
        report["notes"].append("income preview empty — office CSV unchanged")

    owner_preview = exp_dir / "Owner_Draws_Export_Preview.csv"
    _, owner_rows = _read_csv_dicts(owner_preview)
    if owner_rows:
        added, total, notes = merge_preview_into_office_csv(
            paths["owner_draws"],
            owner_rows,
            _owner_draw_key,
            backup_dir,
            source_tag,
        )
        report["owner_draws_added"] = added
        report["owner_draws_total_rows"] = total
        report["notes"].extend(notes)
    else:
        report["notes"].append("owner draws preview empty — office CSV unchanged")

    return report


def run_office_sync(base_dir: Path) -> Dict[str, object]:
    """Run Phases 1-2 office alignment for one install folder."""
    data_dir = Path(os.environ.get("JRC_DATA_DIR", str(base_dir / "data")))
    db_path = Path(os.environ.get("JRC_DB_PATH", str(data_dir / "jr_business.db")))
    report: Dict[str, object] = {
        "base_dir": str(base_dir),
        "db_path": str(db_path),
        "notes": [],
        "errors": [],
    }
    dropbox = find_dropbox_records(base_dir)
    if not dropbox:
        report["errors"].append("dropbox-records not found")
        return report
    report["dropbox_records"] = str(dropbox)
    if not db_path.is_file():
        report["errors"].append(f"database missing: {db_path}")
        return report

    conn = sqlite3.connect(db_path)
    try:
        report["notes"].extend(apply_office_business_standards(conn))
        register_dropbox_file_source(conn, dropbox)
        ins, upd, jnotes = import_job_register(conn, dropbox)
        report["jobs_inserted"] = ins
        report["jobs_updated"] = upd
        report["notes"].extend(jnotes)
        imp, imp_notes = import_payroll_from_office_csv(conn, dropbox)
        report["payroll_rows_imported"] = imp
        report["notes"].extend(imp_notes)
        od_imp, od_notes = import_owner_draws_office(conn, dropbox)
        report["owner_draws_rows_imported"] = od_imp
        report["notes"].extend(od_notes)
        inc_imp, inc_notes = import_income_from_office_csv(conn, dropbox)
        report["income_rows_imported"] = inc_imp
        report["notes"].extend(inc_notes)
        exp_dir = base_dir / "exports" / "office_sync"
        wp = export_worker_payments_csv(conn, exp_dir / "Payroll_Helper_Export_Preview.csv")
        ip = export_income_preview_csv(conn, exp_dir / "Income_Deposit_Export_Preview.csv")
        od = export_owner_draws_preview_csv(conn, exp_dir / "Owner_Draws_Export_Preview.csv")
        report["payroll_rows_exported"] = wp
        report["income_rows_exported"] = ip
        report["owner_draws_rows_exported"] = od
        report["notes"].append(f"exports written to {exp_dir}")
        merge = merge_exports_to_office_records(dropbox, exp_dir)
        report["office_merge"] = merge
        report["payroll_rows_merged"] = merge.get("payroll_added", 0)
        report["income_rows_merged"] = merge.get("income_added", 0)
        report["owner_draws_rows_merged"] = merge.get("owner_draws_added", 0)
        report["notes"].extend(merge.get("notes", []))
        if wp == 0:
            report["notes"].append("payroll export empty — no new program payments to merge")
        if ip == 0:
            report["notes"].append("income export empty — no new program deposits to merge")
        if od == 0:
            report["notes"].append("owner draws export empty — no new owner draws to merge")
        from app.live_chat import ensure_live_chat_schema

        ensure_live_chat_schema(conn)
        report["notes"].append("live chat schema ensured")
    finally:
        conn.close()
    return report


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    base = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    rep = run_office_sync(base)
    print("Office sync:", rep)
    return 1 if rep.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
