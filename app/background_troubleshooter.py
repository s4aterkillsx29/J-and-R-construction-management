"""In-depth automated troubleshooter for JRC — uses unified engine."""
from __future__ import annotations

from pathlib import Path

from app.troubleshooter_engine import run_full_troubleshoot as _run_engine


def run_full_troubleshoot(repair: bool = True) -> Path:
    report_path, _steps = _run_engine(repair=repair)
    return report_path


if __name__ == "__main__":
    p = run_full_troubleshoot(repair=True)
    print("Report saved:", p)
