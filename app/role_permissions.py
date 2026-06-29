# -*- coding: utf-8 -*-
"""Canonical roles and permissions for JRC Construction Manager."""
from __future__ import annotations

ROLE_LABELS = (
    "admin",
    "manager",
    "worker",
    "helper",
    "subcontractor",
    "viewer",
    "guest",
    "non_company",
    "customer",
)

ROLE_DISPLAY_NAMES = {
    "admin": "Owner / Admin",
    "manager": "Office Manager",
    "worker": "Company Employee",
    "helper": "Field Helper",
    "subcontractor": "Subcontractor (1099)",
    "viewer": "Read-only Staff",
    "guest": "Guest / Applicant",
    "non_company": "External Contact",
    "customer": "Customer Portal",
}

PERMISSIONS = {
    "admin": {
        "view_dashboard", "view_jobs", "edit_jobs", "view_money", "edit_money", "view_files", "manage_files",
        "view_workers", "edit_workers", "manage_payroll", "view_admin", "manage_users", "manage_settings",
        "backup", "audit", "share_files", "share_jobs", "view_shared_sessions", "manage_devices",
        "owner_recovery", "mobile_access", "configure_ai", "configure_hosting", "view_bookkeeping",
        "manage_bookkeeping", "view_filekeeping", "manage_filekeeping", "view_applications",
        "manage_applications", "submit_application",
    },
    "manager": {
        "view_dashboard", "view_jobs", "edit_jobs", "view_money", "edit_money", "view_files", "manage_files",
        "view_workers", "edit_workers", "manage_payroll", "backup", "share_files", "share_jobs",
        "view_shared_sessions", "mobile_access", "view_bookkeeping", "manage_bookkeeping",
        "view_filekeeping", "manage_filekeeping", "view_applications", "manage_applications",
        "submit_application",
    },
    "worker": {
        "view_dashboard", "view_jobs", "view_files", "view_shared_sessions", "mobile_access",
        "view_bookkeeping", "view_filekeeping",
    },
    "helper": {
        "view_dashboard", "view_jobs", "view_files", "view_shared_sessions", "mobile_access",
    },
    "subcontractor": {
        "view_dashboard", "view_shared_sessions", "mobile_access", "submit_application",
    },
    "viewer": {
        "view_dashboard", "view_jobs", "view_files", "view_shared_sessions", "mobile_access",
        "view_bookkeeping", "view_filekeeping",
    },
    "guest": {
        "view_dashboard", "mobile_access", "submit_application",
    },
    "non_company": {
        "view_dashboard", "view_shared_sessions", "mobile_access", "submit_application",
    },
    "customer": {
        "view_dashboard", "mobile_access", "customer_portal", "customer_request_job",
        "view_customer_shared",
    },
}

HIRE_APPLICATION_ROLES = ("helper", "worker", "viewer", "subcontractor")
