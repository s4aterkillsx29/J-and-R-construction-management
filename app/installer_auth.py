"""
Installer authentication gate — foolproof verify/create owner before install.

Passwords are verified locally and never written to installer logs.
Success writes data/install_auth.json and logs to install_setup_journal.log.
"""
from __future__ import annotations

try:
    from app.win11_compat import enable_win_dpi_awareness
    enable_win_dpi_awareness()
except Exception:
    pass

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None

from app.install_setup_log import get_suggested_admin_username, log_event, mark_step, users_exist, write_setup_report
from app.local_login_gate import (
    db as login_db,
    ensure_min_schema,
    hash_password,
    now_iso,
    record_event,
    verify_password,
)
from app.role_utils import DEFAULT_OWNER_PASSWORD, DEFAULT_OWNER_USERNAME, normalize_role

AUTH_FILE = "install_auth.json"


def auth_path(base_dir: Path) -> Path:
    return base_dir / "data" / AUTH_FILE


def load_auth(base_dir: Path) -> dict | None:
    path = auth_path(base_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_auth(base_dir: Path, payload: dict) -> None:
    path = auth_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log_event(
        base_dir,
        "Auth",
        f"Saved install auth for {payload.get('username') or 'worker'} role={payload.get('role')}",
        extra={"verified": payload.get("verified"), "profile": payload.get("profile")},
    )


def _bind_gate_paths(base_dir: Path) -> None:
    import app.local_login_gate as gate

    gate.BASE_DIR = base_dir
    gate.DATA_DIR = base_dir / "data"
    gate.DB_PATH = gate.DATA_DIR / "jr_business.db"


def verify_credentials(base_dir: Path, username: str, password: str) -> tuple[bool, str, str]:
    _bind_gate_paths(base_dir)
    ensure_min_schema()
    with login_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND active=1",
            (username.strip(),),
        ).fetchone()
        if not row:
            log_event(base_dir, "Auth", f"Login failed — unknown user {username.strip()}", level="WARN")
            return False, "", "No active account with that username.\n\nIf this is a new PC, click Create First Owner instead."
        if not verify_password(password, row["salt"], row["password_hash"]):
            log_event(base_dir, "Auth", f"Login failed — wrong password for {username.strip()}", level="WARN")
            return False, "", "Password did not match.\n\nTip: first-setup on this PC may still be ivygrows / ivygrows if unchanged."
        role = normalize_role(row["role"])
        if role != (row["role"] or ""):
            conn.execute("UPDATE users SET role=? WHERE id=?", (role, row["id"]))
            conn.commit()
        record_event(username, role, "OK", "Installer auth verified.")
        log_event(base_dir, "Auth", f"Verified login for {username} role={role}")
        return True, role, "Login verified. You can continue install."


def create_owner_account(
    base_dir: Path,
    username: str,
    password: str,
    confirm: str,
    display_name: str,
) -> tuple[bool, str]:
    _bind_gate_paths(base_dir)
    ensure_min_schema()
    username = username.strip()
    if not username:
        return False, "Choose a username."
    if password != confirm:
        return False, "Password and confirm password must match."
    from app.densus_policy import MIN_PASSWORD_LENGTH

    if len(password or "") < MIN_PASSWORD_LENGTH:
        return False, f"Use at least {MIN_PASSWORD_LENGTH} characters for the owner password."
    with login_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if total and conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone() is None:
            return False, "Accounts already exist on this PC.\n\nUse Verify Login with your admin account instead of Create First Owner."
        if conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            return False, "That username already exists.\n\nUse Verify Login instead."
        salt, ph = hash_password(password)
        conn.execute(
            """INSERT INTO users (username, display_name, role, salt, password_hash, active,
               must_change_password, created_at, notes, owner_account)
               VALUES (?, ?, 'admin', ?, ?, 1, 1, ?, ?, 1)""",
            (username, display_name or "Owner", salt, ph, now_iso(), "Created during installer setup wizard."),
        )
        conn.commit()
    record_event(username, "admin", "OK", "Installer created owner account.")
    log_event(base_dir, "Auth", f"Created owner account {username}")
    return True, "Owner account created. You can continue install."


def run_dialog(base_dir: Path, profile: str = "OwnerMaster") -> int:
    if tk is None:
        print("Tkinter unavailable.", file=sys.stderr)
        return 2

    mark_step(base_dir, "verify_login", "in_progress", "Waiting for owner verification")
    has_users = users_exist(base_dir)
    suggested = get_suggested_admin_username(base_dir)
    result = {"ok": False}

    root = tk.Tk()
    root.withdraw()
    win = tk.Toplevel(root)
    win.title("J & R Construction Manager — Step 2: Verify Login")
    win.geometry("580x560")
    win.configure(bg="#0a0a0a")
    win.resizable(False, False)
    win.grab_set()

    tk.Label(win, text="Step 2 of 3 — Verify who is installing", bg="#0a0a0a", fg="#a3e635", font=("Segoe UI", 17, "bold")).pack(
        anchor="w", padx=22, pady=(18, 4)
    )
    intro = (
        "Owner PC: verify your admin login OR create the first owner account.\n"
        "Passwords stay on this PC — they are never saved in the installer log.\n\n"
        "Customers & remote workers: do NOT use this screen — ask Jacob for the web link."
    )
    tk.Label(win, text=intro, bg="#0a0a0a", fg="#a3a3a3", wraplength=520, justify="left", font=("Segoe UI", 10)).pack(
        anchor="w", padx=22, pady=(0, 10)
    )

    hint = "Existing accounts found — use Verify Login." if has_users else "No accounts yet — use Create First Owner."
    tk.Label(win, text=hint, bg="#0a0a0a", fg="#facc15", font=("Segoe UI", 10, "bold"), wraplength=520, justify="left").pack(
        anchor="w", padx=22, pady=(0, 8)
    )

    form = tk.Frame(win, bg="#111111", padx=16, pady=14)
    form.pack(fill="x", padx=22, pady=4)

    def field(row, label, show=None):
        tk.Label(form, text=label, bg="#111111", fg="#f5f5f5").grid(row=row * 2, column=0, sticky="w", pady=(4, 0))
        e = tk.Entry(form, bg="#0f172a", fg="#f5f5f5", insertbackground="#a3e635", width=34, show=show or "")
        e.grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 6))
        return e

    e_user = field(0, "Username")
    e_user.insert(0, suggested)
    e_pass = field(1, "Password", "*")
    e_confirm = field(2, "Confirm password (create owner only)", "*")
    e_name = field(3, "Your name (create owner only)")
    e_name.insert(0, "Jacob Cosentino")

    status = tk.StringVar(value="Choose Verify Login or Create First Owner.")
    tk.Label(win, textvariable=status, bg="#0a0a0a", fg="#737373", wraplength=520, justify="left", font=("Segoe UI", 9)).pack(
        anchor="w", padx=22, pady=(8, 6)
    )

    def finish(ok: bool, username: str = "", role: str = "", message: str = ""):
        if ok:
            payload = {
                "verified": True,
                "username": username,
                "role": role,
                "profile": profile,
                "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "message": message,
                "has_existing_users_before": has_users,
            }
            save_auth(base_dir, payload)
            mark_step(base_dir, "verify_login", "ok", f"Verified {username} ({role})")
            write_setup_report(base_dir)
            result["ok"] = True
            messagebox.showinfo("Verified", f"{message}\n\nStep 3: return to installer and click Install / Update.", parent=win)
            win.destroy()
        else:
            status.set(message.replace("\n", " ")[:200])
            mark_step(base_dir, "verify_login", "error", message[:120])
            messagebox.showerror("Not verified", message, parent=win)

    def on_verify(_event=None):
        ok, role, msg = verify_credentials(base_dir, e_user.get(), e_pass.get())
        if not ok:
            finish(False, message=msg)
            return
        if profile == "OwnerMaster" and role != "admin":
            finish(False, message="Owner Master PC install requires an admin account.")
            return
        finish(True, e_user.get().strip(), role, msg)

    def on_create():
        ok, msg = create_owner_account(base_dir, e_user.get(), e_pass.get(), e_confirm.get(), e_name.get())
        if not ok:
            finish(False, message=msg)
            return
        finish(True, e_user.get().strip(), "admin", msg)

    btns = tk.Frame(win, bg="#0a0a0a")
    btns.pack(fill="x", padx=22, pady=(4, 16))
    tk.Button(btns, text="Verify Login", command=on_verify, bg="#84cc16", fg="#000", relief="flat", padx=14, pady=9).pack(
        side="left", padx=(0, 8)
    )
    tk.Button(btns, text="Create First Owner", command=on_create, bg="#374151", fg="#fff", relief="flat", padx=12, pady=9).pack(
        side="left", padx=(0, 8)
    )
    tk.Button(btns, text="Cancel", command=win.destroy, bg="#1f2937", fg="#fff", relief="flat", padx=12, pady=9).pack(side="right")
    win.bind("<Return>", on_verify)
    e_pass.focus_set()
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    root.wait_window(win)
    root.destroy()
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JRC installer authentication gate")
    parser.add_argument("--install-dir", required=True, help="Target install directory")
    parser.add_argument("--profile", default="OwnerMaster", choices=["OwnerMaster", "WorkerClient"])
    parser.add_argument("--check", action="store_true", help="Return 0 if install_auth.json exists")
    args = parser.parse_args(argv)
    base = Path(args.install_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    (base / "data").mkdir(parents=True, exist_ok=True)
    log_event(base, "Auth", f"Installer auth started profile={args.profile}")
    if args.check:
        auth = load_auth(base)
        return 0 if auth and auth.get("verified") else 1
    if args.profile == "WorkerClient":
        save_auth(
            base,
            {
                "verified": True,
                "username": "",
                "role": "worker",
                "profile": "WorkerClient",
                "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "message": "Worker client — connects via owner host/cloud. No local business database.",
            },
        )
        mark_step(base, "verify_login", "ok", "Worker client — no local owner login required")
        return 0
    return run_dialog(base, profile=args.profile)


if __name__ == "__main__":
    raise SystemExit(main())
