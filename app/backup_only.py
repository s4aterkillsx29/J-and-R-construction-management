"""Command-line backup helper for J and R Construction Manager."""
from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
EVIDENCE_DIR = BASE_DIR / "evidence"
APP_DIR = BASE_DIR / "app"


def main() -> int:
    EXPORT_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    zip_path = EXPORT_DIR / f"J_and_R_Construction_Manager_Backup_{stamp}.zip"
    include_roots = [
        BASE_DIR / "README.txt",
        BASE_DIR / "START_HERE.txt",
        BASE_DIR / "requirements.txt",
        BASE_DIR / "INSTALL_JR_JOB_MANAGER.bat",
        BASE_DIR / "install_jr_job_manager.ps1",
        BASE_DIR / "run_jr_job_manager.bat",
        DATA_DIR / "jr_business.db",
    ]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in include_roots:
            if p.exists() and p.is_file():
                z.write(p, p.relative_to(BASE_DIR))
        for folder in [APP_DIR, EXPORT_DIR, EVIDENCE_DIR]:
            if not folder.exists():
                continue
            for p in folder.rglob("*"):
                if p.is_file() and p != zip_path:
                    z.write(p, p.relative_to(BASE_DIR))
        z.writestr(
            "BACKUP_MANIFEST.txt",
            "J and R Construction Manager backup\n"
            f"Created: {dt.datetime.now().isoformat(timespec='seconds')}\n"
            f"Source folder: {BASE_DIR}\n"
            "This is a program/database backup. It includes files stored in the program evidence folder, not your whole Dropbox unless you copied it into evidence.\n",
        )
    print(f"Backup created: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
