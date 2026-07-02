# -*- coding: utf-8 -*-
"""File and route access security — role-based file visibility for JRC Manager."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

BASE = Path(__file__).resolve().parents[1]

SENSITIVE_NAME_TOKENS = (
    "payroll",
    "w-9",
    "w9",
    "tax_",
    "jrc_tax",
    "internal_workup",
    "internal-workup",
    "helper_pay",
    "owner_labor",
    "owner_draws",
    "bookkeeping",
    "worker_payment",
    "w2",
    "1099",
    "ssn",
    "bank_",
    "account_number",
    "income_deposit",
    "helper_register",
)

SENSITIVE_PATH_TOKENS = (
    "/04_financial_tracking/",
    "/06_bookkeeping",
    "/payroll",
    "/internal_3",
    "/internal_",
    "helper_pay",
    "tax_2026",
)

ADMIN_MANAGER_ROLES = frozenset({"admin", "manager"})


def normalize_role(role: str) -> str:
    from app.role_utils import normalize_role as nr

    return nr(role)


def is_sensitive_business_file(file_path: str) -> bool:
    name = Path(file_path).name.lower()
    path_lower = str(file_path).lower().replace("\\", "/")
    if any(t in name for t in SENSITIVE_NAME_TOKENS):
        return True
    return any(t in path_lower for t in SENSITIVE_PATH_TOKENS)


def role_may_open_indexed_file(role: str, file_path: str) -> Tuple[bool, str]:
    """Return (allowed, reason). Customers/external must use shared files only."""
    r = normalize_role(role)
    if r in ("customer", "guest", "non_company"):
        return False, "This account type cannot browse internal files — open Shared Items only."
    if r == "subcontractor" and is_sensitive_business_file(file_path):
        return False, "Subcontractor accounts cannot open payroll, tax, or internal costing files."
    if is_sensitive_business_file(file_path) and r not in ADMIN_MANAGER_ROLES:
        return False, "Payroll, tax, and internal costing files are restricted to owner/admin and manager."
    return True, "ok"


def get_allowed_file_roots(base_dir: Path) -> List[Path]:
    roots: List[Path] = []
    for rel in ("evidence", "uploads", "exports", "file_sources", "chatgpt_imports", "business_standards", "data"):
        p = base_dir / rel
        if p.exists():
            roots.append(p)
    try:
        from app.office_records_sync import find_dropbox_records

        dbx = find_dropbox_records(base_dir)
        if dbx and dbx.exists():
            roots.append(dbx)
    except Exception:
        pass
    src_rows = []
    try:
        db_path = base_dir / "data" / "jr_business.db"
        if db_path.is_file():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            src_rows = conn.execute(
                "SELECT folder_path FROM file_sources WHERE active=1"
            ).fetchall()
            conn.close()
    except Exception:
        pass
    for row in src_rows:
        try:
            fp = Path(row["folder_path"] if isinstance(row, sqlite3.Row) else row[0])
            if fp.exists():
                roots.append(fp)
        except Exception:
            continue
    return roots


def path_under_allowed_roots(file_path: Path, allowed_roots: List[Path]) -> bool:
    try:
        rp = file_path.resolve()
    except OSError:
        return False
    for root in allowed_roots:
        if not root.exists():
            continue
        try:
            rr = root.resolve()
            if str(rp).lower().startswith(str(rr).lower()):
                return True
        except OSError:
            continue
    return False


def verify_file_access_security(base_dir: Path | None = None) -> int:
    """Static + light dynamic checks for phase verification."""
    base = Path(base_dir or BASE).resolve()
    errors: List[str] = []
    notes: List[str] = []

    ns = (base / "app" / "network_server.py").read_text(encoding="utf-8", errors="ignore")
    rp = (base / "app" / "role_permissions.py").read_text(encoding="utf-8", errors="ignore")

    def check(name: str, ok: bool, fail: str = "") -> None:
        if ok:
            notes.append(f"OK: {name}")
        else:
            errors.append(fail or name)

    check("global login gate", "enforce_global_login_required" in ns)
    check("customer /files blocked in before_request", '"/files"' in ns and "protect_admin_and_sensitive_surfaces" in ns)
    check("shared file role gate", "role_can_access_share" in ns and "open_shared_file" in ns)
    check("file open uses access guard", "file_access_security" in ns and "role_may_open_indexed_file" in ns)
    check("admin-only account approval", "is_admin_role" in ns and "approve_account_request" in ns)
    check("requester notify on decision", "notify_requester_account_decision" in ns)
    check("role change helper", "apply_user_role_change" in ns)
    check("permissions_override wired", "get_user_permissions" in ns and "permissions_override" in ns)
    check("customer lacks view_files", '"customer"' in rp and "view_customer_shared" in rp)
    try:
        from app.role_permissions import PERMISSIONS

        customer_perms = PERMISSIONS.get("customer", set())
        check("customer no internal files perm", "view_files" not in customer_perms)
    except Exception as exc:
        check("customer no internal files perm", False, str(exc))

    check(
        "sensitive payroll blocked for worker",
        not role_may_open_indexed_file("worker", r"C:\biz\Payroll_Helper_Register.csv")[0],
    )
    check(
        "admin may open payroll",
        role_may_open_indexed_file("admin", r"C:\biz\Payroll_Helper_Register.csv")[0],
    )
    check(
        "customer blocked from index",
        not role_may_open_indexed_file("customer", r"C:\biz\quote.pdf")[0],
    )

    with tempfile.TemporaryDirectory() as tmp:
        base_test = Path(tmp)
        (base_test / "evidence").mkdir()
        safe = base_test / "evidence" / "photo.jpg"
        safe.write_text("x", encoding="utf-8")
        outside = Path(tmp) / "outside" / "secret.pdf"
        outside.parent.mkdir()
        outside.write_text("x", encoding="utf-8")
        roots = [base_test / "evidence"]
        check("path under root", path_under_allowed_roots(safe, roots))
        check("path outside root blocked", not path_under_allowed_roots(outside, roots))

    print("FILE ACCESS SECURITY CHECK")
    for n in notes:
        print(f"  {n}")
    for e in errors:
        print(f"  ERROR: {e}")
    print(f"Summary: {len(errors)} error(s)")
    return 1 if errors else 0


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE
    return verify_file_access_security(base)


if __name__ == "__main__":
    raise SystemExit(main())
