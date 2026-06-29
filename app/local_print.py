"""Print local files to Phoswift A42 (or any Windows printer)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PRINTER = os.environ.get("JRC_PRINTER_NAME", "Phoswift A42")


def list_printers() -> list[str]:
    try:
        import win32print

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return [p[2] for p in win32print.EnumPrinters(flags)]
    except Exception:
        return []


def print_file(path: str | Path, printer_name: str = DEFAULT_PRINTER) -> tuple[bool, str]:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return False, f"File not found: {p}"

    candidates = [
        Path(__file__).resolve().parent.parent / "tools" / "Print-JRCFile.ps1",
        Path(__file__).resolve().parents[2] / "tools" / "Print-JRCFile.ps1",
    ]
    ps = next((c for c in candidates if c.is_file()), None)
    if ps:
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps),
            "-Path",
            str(p),
            "-PrinterName",
            printer_name,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return True, (r.stdout or "").strip() or f"Printed via PowerShell: {p.name}"
        return False, (r.stderr or r.stdout or "Print failed").strip()

    # Fallback: text only
    if p.suffix.lower() == ".txt":
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", f'@\'{text}\'@ | Out-Printer -Name "{printer_name}"'],
                check=True,
                capture_output=True,
                text=True,
            )
            return True, f"Printed text: {p.name}"
        except Exception as exc:
            return False, str(exc)

    try:
        os.startfile(str(p), "print")  # type: ignore[attr-defined]
        return True, f"Sent to default handler: {p.name}"
    except Exception as exc:
        return False, str(exc)


def print_files(paths: list[str | Path], printer_name: str = DEFAULT_PRINTER) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    for raw in paths:
        ok, msg = print_file(raw, printer_name)
        out.append((str(raw), ok, msg))
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.local_print <file> [file2 ...]")
        print("Printers:", ", ".join(list_printers()) or "(none)")
        raise SystemExit(1)
    printer = sys.argv[1] if len(sys.argv) > 2 and sys.argv[1].startswith("-P") else DEFAULT_PRINTER
    files = sys.argv[1:] if printer == DEFAULT_PRINTER else sys.argv[2:]
    for path, ok, msg in print_files(files, printer):
        print(("OK" if ok else "FAIL"), path, "-", msg)
        if not ok:
            raise SystemExit(1)
