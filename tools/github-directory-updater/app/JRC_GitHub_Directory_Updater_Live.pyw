"""J&R Construction GitHub Directory Updater - Live v3.4

A small professional Tkinter UI that publishes a selected project directory to GitHub
using normal Git commands. Designed for J&R Construction Manager repo maintenance.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "J&R Construction GitHub Directory Updater - Live v3.4"
SENSITIVE_KEYWORDS = [
    ".env", "secret", "token", "credential", "password", "private", "key",
    "w-9", "w9", "ein", "cp575", "irs", "tax", "bank", "routing",
    "payroll", "receipt", "customer", "backup", "database", ".sqlite", ".db",
]

SECURE_GITIGNORE_BLOCK = """

# --- JRC GitHub Directory Updater security block ---
.env
.env.*
!.env.example
*.pem
*.key
*.p12
*.pfx
id_rsa
id_ed25519
*secret*
*token*
*credential*
credentials.json
service-account*.json
backups/
exports/
uploads/
media/
receipts/
customer_files/
payroll_files/
tax_records/
private_files/
*.db
*.sqlite
*.sqlite3
*.zip
*.rar
*.7z
*W-9*
*W9*
*EIN*
*CP575*
*CP_575*
*IRS*
*tax*
*Tax*
*bank*
*routing*
*payroll*
*Payroll*
*receipt*
*Receipt*
# --- end JRC security block ---
"""


def run_cmd(command: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            shell=False,
        )
        return completed.returncode, (completed.stdout + completed.stderr).strip()
    except FileNotFoundError as exc:
        return 127, f"Command not found: {command[0]}\n{exc}"
    except Exception as exc:  # noqa: BLE001 - UI should report unexpected failures
        return 1, str(exc)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x680")
        self.minsize(860, 560)
        self.project_dir = tk.StringVar()
        self.repo_url = tk.StringVar()
        self.commit_message = tk.StringVar(value="Update JRC project directory")
        self.dry_run = tk.BooleanVar(value=True)
        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(root, text=APP_TITLE, font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w")
        subtitle = ttk.Label(
            root,
            text="Publish a folder/directory to GitHub safely. Dry Run is on by default.",
        )
        subtitle.pack(anchor="w", pady=(0, 12))

        form = ttk.LabelFrame(root, text="Repository Settings", padding=12)
        form.pack(fill=tk.X)

        ttk.Label(form, text="Project folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.project_dir).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(form, text="Browse", command=self.browse).grid(row=0, column=2)

        ttk.Label(form, text="GitHub remote URL").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.repo_url).grid(row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(form, text="Set Remote", command=self.set_remote).grid(row=1, column=2, pady=(8, 0))

        ttk.Label(form, text="Commit message").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.commit_message).grid(row=2, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Checkbutton(form, text="Dry Run", variable=self.dry_run).grid(row=2, column=2, sticky="w", pady=(8, 0))
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(root)
        buttons.pack(fill=tk.X, pady=12)
        ttk.Button(buttons, text="Scan Directory", command=self.scan).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Write/Update .gitignore", command=self.write_gitignore).pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="Git Status", command=self.git_status).pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="Pull Latest", command=self.pull_latest).pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="Publish Directory", command=self.publish).pack(side=tk.LEFT, padx=8)

        log_frame = ttk.LabelFrame(root, text="Review / Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(log_frame, wrap="word", font=("Consolas", 10))
        self.log.pack(fill=tk.BOTH, expand=True)

        self.write("Ready. Select your J&R Construction Manager repo folder and scan before publishing.")

    def write(self, text: str) -> None:
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def folder(self) -> Path | None:
        value = self.project_dir.get().strip()
        if not value:
            messagebox.showwarning("Missing folder", "Select the project folder first.")
            return None
        path = Path(value)
        if not path.exists() or not path.is_dir():
            messagebox.showerror("Invalid folder", "The selected project folder does not exist.")
            return None
        return path

    def browse(self) -> None:
        selected = filedialog.askdirectory(title="Select J&R Construction Manager repo folder")
        if selected:
            self.project_dir.set(selected)
            self.write(f"Selected folder: {selected}")

    def scan(self) -> None:
        folder = self.folder()
        if not folder:
            return
        self.write("\nScanning directory...")
        count = 0
        warnings = []
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".venv", "venv", "node_modules"}]
            for name in files:
                count += 1
                rel = str(Path(root, name).relative_to(folder))
                low = rel.lower()
                if any(keyword in low for keyword in SENSITIVE_KEYWORDS):
                    warnings.append(rel)
        self.write(f"Files scanned: {count}")
        if warnings:
            self.write("Potential private/security files found. Do not publish until reviewed:")
            for item in warnings[:100]:
                self.write(f"  WARNING: {item}")
            if len(warnings) > 100:
                self.write(f"  ...and {len(warnings) - 100} more warnings")
        else:
            self.write("No obvious sensitive filenames found during scan.")

    def write_gitignore(self) -> None:
        folder = self.folder()
        if not folder:
            return
        path = folder / ".gitignore"
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if "JRC GitHub Directory Updater security block" not in current:
            path.write_text(current.rstrip() + SECURE_GITIGNORE_BLOCK, encoding="utf-8")
            self.write("Updated .gitignore with JRC security block.")
        else:
            self.write(".gitignore already contains JRC security block.")

    def set_remote(self) -> None:
        folder = self.folder()
        if not folder:
            return
        url = self.repo_url.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Enter the GitHub remote URL first.")
            return
        code, out = run_cmd(["git", "remote", "remove", "origin"], cwd=folder)
        if code not in {0, 2, 128}:
            self.write(out)
        code, out = run_cmd(["git", "remote", "add", "origin", url], cwd=folder)
        self.write(out or "Remote origin set.")

    def git_status(self) -> None:
        folder = self.folder()
        if folder:
            code, out = run_cmd(["git", "status", "--short"], cwd=folder)
            self.write("\nGit status:")
            self.write(out or "Working tree clean.")

    def pull_latest(self) -> None:
        folder = self.folder()
        if not folder:
            return
        self._run_thread(["git", "pull", "--ff-only"], folder, "Pull latest")

    def publish(self) -> None:
        folder = self.folder()
        if not folder:
            return
        if self.dry_run.get():
            self.write("\nDry Run is ON. Previewing commands only:")
            self.write("git add .")
            self.write(f"git commit -m \"{self.commit_message.get()}\"")
            self.write("git push")
            return
        if not messagebox.askyesno("Publish to GitHub", "Dry Run is off. Publish this directory to GitHub now?"):
            return
        def work() -> None:
            for command in (["git", "add", "."], ["git", "commit", "-m", self.commit_message.get()], ["git", "push"]):
                code, out = run_cmd(command, cwd=folder)
                self.write(f"\n$ {' '.join(command)}")
                self.write(out or f"Exit code {code}")
                if code not in {0, 1}:  # git commit returns 1 when nothing to commit
                    break
        threading.Thread(target=work, daemon=True).start()

    def _run_thread(self, command: list[str], folder: Path, label: str) -> None:
        def work() -> None:
            self.write(f"\n{label}...")
            code, out = run_cmd(command, cwd=folder)
            self.write(out or f"Exit code {code}")
        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
