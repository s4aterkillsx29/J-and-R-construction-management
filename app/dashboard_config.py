# -*- coding: utf-8 -*-
"""Unified role-based dashboard and simplified navigation."""
from __future__ import annotations

from typing import List, Sequence, Tuple

NavItem = Tuple[str, str, str, str]  # key, label, href, permission
Tile = Tuple[str, str, str, str]  # label, href, note, css_class


def build_nav_items(role: str, perms: set[str], *, is_admin: bool, densus_access: bool = False) -> List[NavItem]:
    """Minimal side nav — deep links live on the main dashboard."""
    items: List[NavItem] = [
        ("dashboard", "Home Dashboard", "/", "view_dashboard"),
    ]
    if "customer_portal" in perms:
        items.append(("customer", "My Portal", "/customer", "customer_portal"))
    if "view_shared_sessions" in perms or "view_customer_shared" in perms:
        items.append(("sharing", "Shared With Me", "/sharing", "view_shared_sessions"))
    if "mobile_access" in perms:
        items.append(("mobile", "Mobile", "/mobile", "mobile_access"))
    if "view_dashboard" in perms:
        items.append(("chat", "Live Chat", "/chat", "view_dashboard"))
    if role in {"guest", "non_company"} or "submit_application" in perms:
        items.append(("apply", "Apply to Work", "/apply", "view_dashboard"))
    if "view_admin" in perms:
        items.append(("admin", "Admin Hub", "/admin", "view_admin"))
    if "configure_ai" in perms and is_admin:
        items.append(("office-ai", "Office AI", "/office-ai", "configure_ai"))
    if is_admin and densus_access:
        items.append(("densus", "Security Monitor", "/admin/densus", "view_admin"))
    elif is_admin:
        items.append(("densus", "Request Densus", "/admin/densus", "view_admin"))
    if "configure_hosting" in perms:
        items.append(("hosting", "Hosting Setup", "/hosting", "configure_hosting"))
    if "audit" in perms:
        items.append(("health", "System Check", "/health", "audit"))
    return [(k, l, h, p) for k, l, h, p in items if p in perms or k == "apply"]


def dashboard_tiles(role: str, perms: set[str], *, densus_access: bool = False) -> List[Tuple[str, str, List[Tile]]]:
    """Grouped action tiles for the main dashboard — replaces scattered nav duplicates."""
    sections: List[Tuple[str, str, List[Tile]]] = []

    def add(title: str, note: str, tiles: List[Tile]) -> None:
        visible = [t for t in tiles if t]
        if visible:
            sections.append((title, note, visible))

    work: List[Tile] = []
    if "view_jobs" in perms:
        work.append(("Jobs", "/jobs", "Active jobs and job codes", ""))
    if "view_jobs" in perms:
        work.append(("Job Pipeline", "/mobile/pipeline", "Field pipeline view", "btn2"))
    if "view_files" in perms:
        work.append(("Files", "/files", "Job folders and evidence", "btn2"))
    if "view_shared_sessions" in perms or "view_customer_shared" in perms:
        work.append(("Shared Items", "/sharing", "Items shared to your account", "btn2"))
    if "view_applications" in perms:
        work.append(("Worker Applications", "/applications", "Review hire applications", "btn2"))
    if role in {"guest", "non_company"} or role == "helper":
        work.append(("Apply for Work", "/apply", "Employee/helper application form", ""))
    add("Work & Field", "Daily job tools for your role.", work)

    customer: List[Tile] = []
    if "customer_request_job" in perms:
        customer.append(("New Job Request", "/customer/request", "Request work from J&R", ""))
        customer.append(("My Requests", "/customer/requests", "Track your requests", "btn2"))
    add("Customer", "Customer-only requests and shared items.", customer)

    money: List[Tile] = []
    if "view_money" in perms:
        money.append(("Invoices", "/invoices", "Customer invoices", ""))
        money.append(("Expenses", "/expenses", "Materials and costs", "btn2"))
        money.append(("Job Costs", "/job-costs", "Per-job profit view", "btn2"))
    if "manage_payroll" in perms:
        money.append(("Payroll", "/payroll", "Helper pay register", "btn2"))
    if "view_bookkeeping" in perms:
        money.append(("Bookkeeping", "/bookkeeping", "Tax and ledger tools", "btn2"))
    add("Money & Books", "Owner/manager financial tools.", money)

    people: List[Tile] = []
    if "edit_jobs" in perms:
        people.append(("Customers", "/customers", "Customer records", ""))
        people.append(("Customer Requests", "/customers/requests", "Inbound customer work", "btn2"))
    if "view_workers" in perms:
        people.append(("Workers / Helpers", "/payroll", "Helper roster and payroll", "btn2"))
    if "manage_users" in perms:
        people.append(("User Accounts", "/admin", "Login accounts and roles", "btn2"))
    add("People", "Customers, workers, and accounts.", people)

    admin: List[Tile] = []
    if "configure_ai" in perms and role == "admin":
        admin.append(("Office AI", "/office-ai", "In-app office assistant (owner/admin only)", ""))
        admin.append(("AI Settings", "/ai", "Provider keys and sources", "btn2"))
    if "view_admin" in perms:
        admin.append(("Admin Hub", "/admin", "Users, sessions, pending logins", ""))
        admin.append(("Review Login Requests", "/admin#pending-requests", "Approve/deny /register", "btn2"))
        admin.append(("Database Editor", "/admin/database/accounts", "Account permissions", "btn2"))
        admin.append(("Dropbox Sync", "/admin/dropbox", "Office records alignment", "btn2"))
    if densus_access:
        admin.append(("Densus Security", "/admin/densus", "Owner-approved session monitor", "btn2"))
    if "view_applications" in perms:
        admin.append(("Worker Applications", "/applications", "Full /apply hire queue", "btn2"))
    if "manage_devices" in perms:
        admin.append(("Devices", "/admin/devices", "Trusted PCs and phones", "btn2"))
    if "configure_hosting" in perms:
        admin.append(("Cloud / Hosting", "/cloud", "Remote access setup", "btn2"))
    if "backup" in perms:
        admin.append(("Data & Backups", "/data", "Export and backup", "btn2"))
    if "audit" in perms:
        admin.append(("Payment Admin", "/admin/payments", "Request payment, lock user, ledger", "btn2"))
        admin.append(("Troubleshooter", "/health", "System verification", "btn2"))
        admin.append(("Setup / Verification", "/setup-status", "System check + security audit", "btn2"))
    add("Admin & Setup", "Owner setup, security, and hosting.", admin)

    account: List[Tile] = [
        ("Change Password", "/account/change-password", "Required after first login", "btn2"),
        ("Mobile Portal", "/mobile", "Phone-friendly view", "btn2"),
        ("Live Chat", "/mobile/messages", "Team chat + announcements", "btn2"),
        ("Field Capture", "/mobile/capture", "Photos and jobsite notes", "btn2"),
    ]
    add("My Account", "Security and mobile access.", account)

    return sections


def render_dashboard_sections(role: str, perms: set[str], *, densus_access: bool = False) -> str:
    """HTML for grouped dashboard tiles."""
    parts = []
    for title, note, tiles in dashboard_tiles(role, perms, densus_access=densus_access):
        buttons = "".join(
            f"<a class='btn {css}' href='{href}'><b>{label}</b><br><span class='muted' style='font-size:12px;font-weight:400'>{note}</span></a>"
            for label, href, note, css in tiles
        )
        parts.append(
            f"<div class='card'><h2>{title}</h2><p class='muted'>{note}</p>"
            f"<div class='action-grid'>{buttons}</div></div>"
        )
    return "".join(parts)
