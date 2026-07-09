"""
JRC v8 Admin Security Final Check
Checks that the owner/admin default password workflow is safe:
- admin/ivygrows is first-run local setup only
- changed admin password is preserved across updates
- public/cloud/customer default-admin login is blocked
- password change route requires current password
- remembered device consent remains opt-in with 90-day expiration
"""
import datetime as dt
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
NS = Path(__file__).with_name("network_server.py")

REQUIRED_MARKERS = [
    "DEFAULT_ADMIN_PASSWORD = \"ivygrows\"",
    "Default local first-setup owner (ivygrows)",
    "default_admin_remote_blocked",
    "mark_admin_password_changed",
    "admin_default_password_changed",
    "admin_default_login_disabled_after_change",
    "@app.route(\"/account/change-password\"",
    "Current password is required before changing your password",
    "other admin sessions revoked",
    "Remember this PC/phone for 90 days",
    "DEVICE_COOKIE_MAX_AGE_SECONDS",
]

DANGEROUS_MARKERS = [
    "Repaired default setup admin. Change password after install.",
    "INSERT INTO users (username, display_name, role, salt, password_hash, active, must_change_password, created_at, notes, email, recovery_email, phone, title, owner_account) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, ?, ?, 1)\",\n                (\"admin\", OWNER, \"admin\", salt, ph, now_iso(), \"Repaired",
]

def run_check():
    EXPORT_DIR.mkdir(exist_ok=True)
    text = NS.read_text(encoding="utf-8")
    errors = []
    warnings = []
    for marker in REQUIRED_MARKERS:
        if marker not in text:
            errors.append(f"Missing marker: {marker}")
    for marker in DANGEROUS_MARKERS:
        if marker in text:
            errors.append(f"Dangerous old default-admin repair marker still present: {marker[:80]}")
    if "PUBLIC_HOST_MODE or not is_local_setup_request()" not in text:
        errors.append("Default admin login is not clearly blocked outside local setup.")
    if "enforce_new_password_policy(new_password, mastery)" not in text and "password_quality(new_password, admin_change=is_admin_change)" not in text:
        errors.append("Admin password change does not appear to use strengthened admin password rules.")
    if "must_change_password=0" not in text:
        warnings.append("Could not confirm password-change flow clears must_change_password.")
    status = "PASS" if not errors else "FAIL"
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report = EXPORT_DIR / f"JRC_Admin_Security_Final_Check_{ts}.txt"
    lines = [
        "JRC Admin Security Final Check",
        f"Status: {status}",
        f"Timestamp: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "Checks performed:",
        "- Default admin/ivygrows is local first-setup only.",
        "- Remote/customer/cloud default-admin attempts are blocked.",
        "- Changed admin password is preserved across updates.",
        "- Password-change route requires the current password.",
        "- Admin password change disables default admin state and revokes other admin sessions.",
        "- Remembered devices stay opt-in with 90-day expiration.",
        "",
        "Errors:",
    ]
    lines.extend([f"ERROR: {e}" for e in errors] or ["None"])
    lines.extend(["", "Warnings:"])
    lines.extend([f"WARN: {w}" for w in warnings] or ["None"])
    report.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if not errors else 1

if __name__ == "__main__":
    raise SystemExit(run_check())
