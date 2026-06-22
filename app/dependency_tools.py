"""
Dependency helpers for J and R Construction Manager.
Standard-library only. Used by Start Center and System Check.
"""
from __future__ import annotations
import importlib.util
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
VENV_PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PY) if VENV_PY.exists() else sys.executable
REQUIREMENTS = BASE_DIR / "requirements.txt"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

OPTIONAL_MODULES = {
    "flask": "Network/shared-session hosting and mobile browser access",
    "waitress": "Production-style Windows web server runner",
    "reportlab": "PDF invoice/estimate generation",
}


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def dependency_status() -> dict[str, bool]:
    return {name: module_available(name) for name in OPTIONAL_MODULES}


def missing_dependencies() -> list[str]:
    return [name for name, ok in dependency_status().items() if not ok]


def status_text() -> str:
    lines = []
    for name, desc in OPTIONAL_MODULES.items():
        lines.append(f"{'OK' if module_available(name) else 'MISSING'} - {name}: {desc}")
    return "\n".join(lines)


def install_optional_dependencies(timeout: int = 300) -> tuple[bool, str]:
    if not REQUIREMENTS.exists():
        return False, f"Missing requirements file: {REQUIREMENTS}"
    log = LOG_DIR / "dependency_repair_last.log"
    cmd = [PYTHON, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--no-warn-script-location", "--default-timeout", "60", "-r", str(REQUIREMENTS)]
    try:
        result = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=timeout)
        log.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8", errors="replace")
        if result.returncode == 0:
            return True, f"Optional dependencies installed. Log saved: {log}"
        return False, f"Dependency install returned code {result.returncode}. Log saved: {log}"
    except subprocess.TimeoutExpired:
        return False, f"Dependency install timed out after {timeout} seconds. Log saved: {log}"
    except Exception as exc:
        return False, f"Dependency install failed: {exc}"


if __name__ == "__main__":
    print("J and R dependency status before repair:")
    print(status_text())
    ok, msg = install_optional_dependencies(timeout=300)
    print(msg)
    print("\nStatus after repair attempt:")
    print(status_text())
    raise SystemExit(0 if ok else 1)
