# -*- coding: utf-8 -*-
"""Job application email notifications — owner inbox + applicant status updates."""
from __future__ import annotations

import os
import re
import smtplib
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_OWNER_EMAIL = "enragementwow@hotmail.com"
BUSINESS_NAME = "J & R Construction"
PHONE = "(910) 712-0936"

FIELD_LABELS = [
    ("id", "Application #"),
    ("status", "Status"),
    ("created_at", "Submitted"),
    ("full_name", "Full legal name"),
    ("requested_username", "Desired username"),
    ("desired_role", "Desired role"),
    ("email", "Email"),
    ("recovery_email", "Recovery email"),
    ("phone", "Phone"),
    ("address", "Address"),
    ("date_of_birth", "Date of birth"),
    ("emergency_contact_name", "Emergency contact"),
    ("emergency_contact_phone", "Emergency phone"),
    ("preferred_rate", "Preferred rate"),
    ("rate_type", "Rate type"),
    ("availability", "Availability"),
    ("transportation", "Transportation"),
    ("drivers_license_status", "Driver license"),
    ("own_tools", "Tools / equipment"),
    ("skills", "Skills"),
    ("experience_years", "Years experience"),
    ("work_history", "Work history"),
    ("references_text", "References"),
    ("insurance_full_legal_name", "Insurance legal name"),
    ("insurance_address", "Insurance address"),
    ("insurance_phone", "Insurance phone"),
    ("insurance_email", "Insurance email"),
    ("insurance_date_of_birth", "Insurance DOB"),
    ("insurance_driver_license_state", "DL state"),
    ("insurance_driver_license_number", "DL number"),
    ("insurance_vehicle_use", "Vehicle use"),
    ("insurance_employment_classification", "Classification"),
    ("insurance_requested_coverage", "Coverage / duties"),
    ("w9_status", "W-9 status"),
    ("id_document_status", "ID document status"),
    ("insurance_notes", "Insurance notes"),
    ("owner_notes", "Owner notes"),
    ("request_ip", "Submitted from IP"),
]


def _base_dir() -> Path:
    return Path(os.environ.get("JRC_LIVE_DIR", Path(__file__).resolve().parents[1]))


def _outbox_dir() -> Path:
    d = _base_dir() / "data" / "application_email_outbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dropbox_inbox() -> Optional[Path]:
    try:
        from app.jrc_workspace import resolve_workspace, workspace_layout

        root = resolve_workspace(_base_dir())
        if root:
            dest = workspace_layout(root)["admin"] / "Job_Application_Inbox"
            dest.mkdir(parents=True, exist_ok=True)
            return dest
    except Exception:
        pass
    return None


def get_owner_email(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key='owner_notification_email'").fetchone()
        if row and str(row[0]).strip():
            return str(row[0]).strip()
    except sqlite3.Error:
        pass
    env = os.environ.get("JRC_OWNER_EMAIL", "").strip()
    if env:
        return env
    try:
        admin = conn.execute(
            "SELECT email FROM users WHERE role='admin' AND active=1 AND email IS NOT NULL AND email != '' "
            "ORDER BY owner_account DESC, id LIMIT 1"
        ).fetchone()
        if admin and admin[0]:
            return str(admin[0]).strip()
    except sqlite3.Error:
        pass
    return DEFAULT_OWNER_EMAIL


def _smtp_settings(conn: Optional[sqlite3.Connection] = None) -> Dict[str, str]:
    keys = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from")
    settings: Dict[str, str] = {}
    if conn:
        try:
            for key in keys:
                row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
                if row and str(row[0]).strip():
                    settings[key] = str(row[0]).strip()
        except sqlite3.Error:
            pass
    env_map = {
        "smtp_host": "JRC_SMTP_HOST",
        "smtp_port": "JRC_SMTP_PORT",
        "smtp_user": "JRC_SMTP_USER",
        "smtp_password": "JRC_SMTP_PASSWORD",
        "smtp_from": "JRC_SMTP_FROM",
    }
    for key, env_key in env_map.items():
        if not settings.get(key):
            val = os.environ.get(env_key, "").strip()
            if val:
                settings[key] = val
    if not settings.get("smtp_host"):
        settings["smtp_host"] = "smtp-mail.outlook.com"
    if not settings.get("smtp_port"):
        settings["smtp_port"] = "587"
    if not settings.get("smtp_from") and settings.get("smtp_user"):
        settings["smtp_from"] = settings["smtp_user"]
    return settings


def application_row_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def format_application_body(app: Dict[str, Any], *, status_url: str = "") -> str:
    lines = [
        f"{BUSINESS_NAME} — Worker / Job Application",
        f"Phone: {PHONE}",
        "=" * 50,
        "",
    ]
    for key, label in FIELD_LABELS:
        val = app.get(key)
        if val is None or str(val).strip() == "":
            continue
        lines.append(f"{label}: {val}")
    if status_url:
        lines.extend(["", f"Applicant status link: {status_url}"])
    lines.extend(["", "— Sent by JRC Construction Manager"])
    return "\n".join(lines)


def _save_outbox_copy(filename_stem: str, subject: str, body: str, to_addr: str) -> Path:
    outbox = _outbox_dir()
    path = outbox / f"{filename_stem}.txt"
    path.write_text(f"TO: {to_addr}\nSUBJECT: {subject}\n\n{body}", encoding="utf-8")
    dropbox = _dropbox_inbox()
    if dropbox:
        try:
            (dropbox / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
    return path


def send_email(to_addr: str, subject: str, body: str, conn: Optional[sqlite3.Connection] = None) -> Tuple[bool, str]:
    to_addr = (to_addr or "").strip()
    if not to_addr or "@" not in to_addr:
        return False, "invalid recipient"

    stamp = re.sub(r"[^\w\-]", "_", subject)[:60]
    _save_outbox_copy(f"{stamp}_{to_addr.split('@')[0]}", subject, body, to_addr)

    smtp = _smtp_settings(conn)
    user = smtp.get("smtp_user", "")
    password = smtp.get("smtp_password", "")
    if not user or not password:
        return False, (
            f"Email saved to data/application_email_outbox/ for {to_addr}. "
            "Set JRC_SMTP_USER and JRC_SMTP_PASSWORD (or app_settings smtp_user/smtp_password) to send live."
        )

    msg = MIMEMultipart()
    msg["From"] = smtp.get("smtp_from") or user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        host = smtp["smtp_host"]
        port = int(smtp.get("smtp_port") or 587)
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
            server.sendmail(msg["From"], [to_addr], msg.as_string())
        return True, f"Email sent to {to_addr}"
    except Exception as exc:
        return False, f"SMTP failed ({exc}); copy saved in application_email_outbox/"


def applicant_email(app: Dict[str, Any]) -> str:
    for key in ("email", "recovery_email", "insurance_email"):
        val = (app.get(key) or "").strip()
        if val and "@" in val:
            return val
    return ""


def build_status_url(app_id: int, token: str, base_url: str = "") -> str:
    base = (base_url or os.environ.get("JRC_CLOUD_BASE_URL", "")).rstrip("/")
    if not base:
        port = os.environ.get("JRC_PORT", "8765")
        base = f"http://127.0.0.1:{port}"
    return f"{base}/apply/status/{app_id}/{token}"


def notify_owner_new_application(
    conn: sqlite3.Connection,
    app_id: int,
    *,
    request_base_url: str = "",
) -> Tuple[bool, str]:
    row = conn.execute("SELECT * FROM job_applications WHERE id=?", (app_id,)).fetchone()
    if not row:
        return False, "application not found"
    app = application_row_dict(row)
    owner = get_owner_email(conn)
    token = app.get("status_token") or ""
    status_url = build_status_url(app_id, token, request_base_url) if token else ""
    body = format_application_body(app, status_url=status_url)
    body = (
        f"NEW JOB APPLICATION — OWNER REVIEW REQUIRED\n"
        f"Application #{app_id} is waiting for your review in JRC Manager → Applications.\n\n"
        + body
    )
    subject = f"[JRC] New worker application #{app_id} — {app.get('full_name', 'Applicant')}"
    ok, msg = send_email(owner, subject, body, conn)
    ts = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE job_applications SET owner_notified_at=?, updated_at=? WHERE id=?",
        (ts, ts, app_id),
    )
    conn.commit()
    return ok, msg


def notify_applicant_status_update(
    conn: sqlite3.Connection,
    app_id: int,
    new_status: str,
    owner_notes: str = "",
    *,
    request_base_url: str = "",
) -> Tuple[bool, str]:
    row = conn.execute("SELECT * FROM job_applications WHERE id=?", (app_id,)).fetchone()
    if not row:
        return False, "application not found"
    app = application_row_dict(row)
    to = applicant_email(app)
    if not to:
        return False, "applicant has no email on file"

    token = app.get("status_token") or ""
    status_url = build_status_url(app_id, token, request_base_url) if token else ""
    notes_block = f"\nOwner notes:\n{owner_notes}\n" if owner_notes else ""
    body = (
        f"Hello {app.get('full_name', '')},\n\n"
        f"Your J & R Construction job application (#{app_id}) status was updated.\n\n"
        f"New status: {new_status}\n"
        f"{notes_block}\n"
        f"This is not a job offer or insurance approval until Jacob completes onboarding.\n"
    )
    if status_url:
        body += f"\nCheck your application status anytime:\n{status_url}\n"
    body += f"\nQuestions? Call {PHONE}\n\n— {BUSINESS_NAME}"

    subject = f"[JRC] Application #{app_id} — {new_status}"
    ok, msg = send_email(to, subject, body, conn)
    ts = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE job_applications SET applicant_notified_status=?, applicant_notified_at=?, updated_at=? WHERE id=?",
        (new_status, ts, ts, app_id),
    )
    conn.commit()
    return ok, msg


def ensure_notification_columns(conn: sqlite3.Connection) -> None:
    for stmt in (
        "ALTER TABLE job_applications ADD COLUMN status_token TEXT",
        "ALTER TABLE job_applications ADD COLUMN owner_notified_at TEXT",
        "ALTER TABLE job_applications ADD COLUMN applicant_notified_status TEXT",
        "ALTER TABLE job_applications ADD COLUMN applicant_notified_at TEXT",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    ensure_account_request_notification_columns(conn)


def requester_email(req: Dict[str, Any]) -> str:
    for key in ("email", "recovery_email"):
        val = (req.get(key) or "").strip()
        if val and "@" in val:
            return val
    return ""


def format_account_request_body(req: Dict[str, Any], *, admin_url: str = "") -> str:
    lines = [
        f"{BUSINESS_NAME} — Account Access Request",
        f"Phone: {PHONE}",
        "=" * 50,
        "",
        f"Request ID: {req.get('id', '')}",
        f"Status: {req.get('status', 'Pending')}",
        f"Submitted: {req.get('created_at', '')}",
        f"Username requested: {req.get('requested_username', '')}",
        f"Full name: {req.get('display_name', '')}",
        f"Role requested: {req.get('requested_role', '')}",
        f"Email: {req.get('email', '')}",
        f"Phone: {req.get('phone', '')}",
        f"Address: {req.get('address', '')}",
        f"Worker type: {req.get('worker_type', '')}",
        f"Skills: {req.get('skills', '')}",
        f"Emergency contact: {req.get('emergency_contact', '')}",
        f"Preferred rate: {req.get('preferred_rate', '')}",
        f"Submitted from IP: {req.get('request_ip', '')}",
        "",
        "Owner/admin must approve in JRC Manager → Admin → Pending Account Requests.",
        "No login exists until approved.",
    ]
    if admin_url:
        lines.extend(["", f"Admin review: {admin_url}"])
    lines.extend(["", "— Sent by JRC Construction Manager"])
    return "\n".join(lines)


def _save_account_outbox(filename_stem: str, subject: str, body: str, to_addr: str) -> Path:
    outbox = _base_dir() / "data" / "account_request_email_outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / f"{filename_stem}.txt"
    path.write_text(f"TO: {to_addr}\nSUBJECT: {subject}\n\n{body}", encoding="utf-8")
    dropbox = _dropbox_inbox()
    if dropbox:
        acct_inbox = dropbox.parent / "Account_Request_Inbox"
        try:
            acct_inbox.mkdir(parents=True, exist_ok=True)
            (acct_inbox / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
    return path


def send_account_email(to_addr: str, subject: str, body: str, conn: Optional[sqlite3.Connection] = None) -> Tuple[bool, str]:
    stamp = re.sub(r"[^\w\-]", "_", subject)[:50]
    _save_account_outbox(f"{stamp}_{to_addr.split('@')[0]}", subject, body, to_addr)
    return send_email(to_addr, subject, body, conn)


def ensure_account_request_notification_columns(conn: sqlite3.Connection) -> None:
    for stmt in (
        "ALTER TABLE account_requests ADD COLUMN owner_notified_at TEXT",
        "ALTER TABLE account_requests ADD COLUMN requester_notified_at TEXT",
        "ALTER TABLE account_requests ADD COLUMN requester_notified_status TEXT",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()


def notify_owner_new_account_request(
    conn: sqlite3.Connection,
    req_id: int,
    *,
    request_base_url: str = "",
) -> Tuple[bool, str]:
    row = conn.execute("SELECT * FROM account_requests WHERE id=?", (req_id,)).fetchone()
    if not row:
        return False, "account request not found"
    req = application_row_dict(row)
    owner = get_owner_email(conn)
    admin_url = f"{request_base_url.rstrip('/')}/admin" if request_base_url else "/admin"
    body = (
        f"NEW ACCOUNT REQUEST — OWNER/ADMIN APPROVAL REQUIRED\n"
        f"Request #{req_id} is Pending. Approve or deny in JRC Manager → Admin.\n\n"
        + format_account_request_body(req, admin_url=admin_url)
    )
    subject = f"[JRC] Account request #{req_id} — {req.get('requested_username', 'user')} (approval required)"
    ok, msg = send_account_email(owner, subject, body, conn)
    ts = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE account_requests SET owner_notified_at=? WHERE id=?", (ts, req_id))
    conn.commit()
    return ok, msg


def notify_requester_account_decision(
    conn: sqlite3.Connection,
    req_id: int,
    decision: str,
    role: str = "",
    *,
    request_base_url: str = "",
) -> Tuple[bool, str]:
    row = conn.execute("SELECT * FROM account_requests WHERE id=?", (req_id,)).fetchone()
    if not row:
        return False, "account request not found"
    req = application_row_dict(row)
    to = requester_email(req)
    if not to:
        return False, "requester has no email on file"

    login_url = f"{request_base_url.rstrip('/')}/login" if request_base_url else "/login"
    username = req.get("requested_username", "")

    if decision == "Approved":
        body = (
            f"Hello {req.get('display_name', '')},\n\n"
            f"Your J & R Construction Manager account request was approved by the owner/admin.\n\n"
            f"Username: {username}\n"
            f"Role: {role or req.get('requested_role', '')}\n\n"
            f"Sign in with the username and password you chose when you submitted the request:\n"
            f"{login_url}\n\n"
            f"Questions? Call {PHONE}\n\n— {BUSINESS_NAME}"
        )
        subject = f"[JRC] Account approved — sign in as {username}"
    else:
        body = (
            f"Hello {req.get('display_name', '')},\n\n"
            f"Your account request for username '{username}' was reviewed and not approved at this time.\n\n"
            f"Contact Jacob at {PHONE} if you have questions.\n\n— {BUSINESS_NAME}"
        )
        subject = f"[JRC] Account request — {username}"

    ok, msg = send_account_email(to, subject, body, conn)
    ts = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE account_requests SET requester_notified_status=?, requester_notified_at=? WHERE id=?",
        (decision, ts, req_id),
    )
    conn.commit()
    return ok, msg
