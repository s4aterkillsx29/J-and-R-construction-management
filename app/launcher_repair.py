"""Repair Windows launchers that break `from app.*` imports (script vs module mode)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]

REPLACEMENTS = {
    "app\\network_server.py": "-m app.network_server",
    "app\\system_check.py": "-m app.system_check",
    "app\\start_center.py": "-m app.start_center",
    "app\\background_troubleshooter.py": "-m app.background_troubleshooter",
    "app\\auto_host_repair.py": "-m app.auto_host_repair",
    "app\\jr_job_manager.py": "-m app.jr_job_manager",
    "app\\backup_only.py": "-m app.backup_only",
}

WATCH_FILES = [
    "START_NETWORK_SERVER.bat",
    "RUN_FULL_SYSTEM_CHECK.bat",
    "run_jr_manager.bat",
    "RUN_BACKGROUND_TROUBLESHOOTER.bat",
    "run_jr_job_manager.bat",
    "make_backup_zip.bat",
]


def repair_launcher_files(base_dir: Path | None = None) -> List[str]:
    root = (base_dir or BASE_DIR).resolve()
    actions: List[str] = []

    for name in WATCH_FILES:
        path = root / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        new_text = text
        for old, new in REPLACEMENTS.items():
            new_text = new_text.replace(old, new)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            actions.append(f"Fixed {name} — now uses Python -m app.* module mode.")
        elif "-m app." in text:
            actions.append(f"OK: {name} already uses module mode.")

    vbs = root / "run_jr_manager_hidden.vbs"
    if vbs.exists():
        text = vbs.read_text(encoding="utf-8", errors="replace")
        if "app\\start_center.py" in text:
            vbs.write_text(
                """Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
Base = FSO.GetParentFolderName(WScript.ScriptFullName)
EnsurePs1 = Base & "\\scripts\\Ensure-DesktopShortcuts.ps1"
If FSO.FileExists(EnsurePs1) Then
  WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & EnsurePs1 & Chr(34) & " -InstallDir " & Chr(34) & Base & Chr(34) & " -Quiet", 0, False
End If
Pyw = Base & "\\.venv\\Scripts\\pythonw.exe"
Py = Base & "\\.venv\\Scripts\\python.exe"
ModuleArgs = "-m app.start_center"
If FSO.FileExists(Pyw) Then
  WshShell.Run Chr(34) & Pyw & Chr(34) & " " & ModuleArgs, 0, False
ElseIf FSO.FileExists(Py) Then
  WshShell.Run Chr(34) & Py & Chr(34) & " " & ModuleArgs, 0, False
Else
  WshShell.Run "pyw -3 " & ModuleArgs, 0, False
End If
""",
                encoding="utf-8",
            )
            actions.append("Fixed run_jr_manager_hidden.vbs — now uses -m app.start_center.")
        elif "-m app.start_center" in text:
            actions.append("OK: run_jr_manager_hidden.vbs already uses module mode.")

    return actions


def verify_app_imports(base_dir: Path | None = None) -> Tuple[bool, str]:
    root = (base_dir or BASE_DIR).resolve()
    py = root / ".venv" / "Scripts" / "python.exe"
    exe = str(py) if py.exists() else sys.executable
    try:
        proc = subprocess.run(
            [exe, "-c", "import app.network_server, app.start_center, app.system_check"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0:
            return True, "Core modules (network_server, start_center, system_check) import OK."
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err[-600:] if err else "Import check failed."
    except Exception as exc:
        return False, str(exc)
