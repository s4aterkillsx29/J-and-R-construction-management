# -*- coding: utf-8 -*-
"""Background Guardian scheduler — Light/Normal/Full profiles, never blocks UI."""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

from app.reliability import guardian_store, repair_policy

_lock = threading.Lock()
_scheduler: Optional["GuardianScheduler"] = None


def _ram_gb() -> float:
    try:
        import psutil

        return psutil.virtual_memory().total / (1024**3)
    except Exception:
        return 8.0


def default_profile() -> str:
    env = os.environ.get("JRC_GUARDIAN_PROFILE", "").strip().lower()
    if env in {"off", "light", "normal", "full"}:
        return env
    return "light" if _ram_gb() <= 8 else "normal"


class GuardianScheduler:
    """Daemon thread runs Light scans after idle; admin can Run Now."""

    def __init__(self, base_dir=None, on_status: Optional[Callable[[str], None]] = None):
        from pathlib import Path

        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parents[2]
        self.on_status = on_status or (lambda _m: None)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._last_activity = time.time()

    def touch_activity(self) -> None:
        self._last_activity = time.time()

    def start(self) -> None:
        with _lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="jrc-guardian")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_now(self, profile: str = "") -> dict:
        """Sync run for admin Run Now — still bounded by profile timeout."""
        prof = profile or default_profile()
        return self._run_cycle(prof)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn = guardian_store.connect()
                try:
                    if guardian_store.get_setting(conn, "enabled", "1") != "1":
                        time.sleep(30)
                        continue
                    prof = guardian_store.get_setting(conn, "profile", default_profile())
                    idle_min = 30 if prof == "light" else 15
                    if time.time() - self._last_activity < idle_min * 60:
                        time.sleep(10)
                        continue
                    if not self._running:
                        self._running = True
                        threading.Thread(
                            target=self._run_cycle_async,
                            args=(prof,),
                            daemon=True,
                        ).start()
                finally:
                    conn.close()
            except Exception:
                pass
            time.sleep(20)

    def _run_cycle_async(self, profile: str) -> None:
        try:
            self._run_cycle(profile)
        finally:
            self._running = False

    def _run_cycle(self, profile: str) -> dict:
        if profile == "off":
            return {"ok": True, "skipped": True, "profile": profile}
        self.on_status(f"Guardian {profile} scan...")
        conn = guardian_store.connect()
        results: dict = {"ok": True, "profile": profile, "checks": []}
        try:
            timeout = {"light": 5, "normal": 8, "full": 30}.get(profile, 5)
            deadline = time.time() + timeout
            checks = [
                ("venv_check", self._check_venv),
                ("folder_check", self._check_folders),
                ("host_ping", self._check_host),
            ]
            if profile in {"normal", "full"}:
                checks.append(("deps_check", self._check_deps))
            if profile == "full":
                checks.append(("consistency_read", self._check_consistency))
            auto = guardian_store.get_setting(conn, "auto_repair", "1") == "1"
            for name, fn in checks:
                if time.time() > deadline:
                    results["checks"].append({"name": name, "level": "WARN", "message": "timeout"})
                    break
                try:
                    level, msg = fn()
                    tier = repair_policy.repair_tier(name)
                    fixed = False
                    if level == "ERROR" and repair_policy.can_auto_repair(name, auto_repair_enabled=auto):
                        level, msg = "FIXED", f"Auto-repaired: {msg}"
                        fixed = True
                    guardian_store.log_event(
                        conn,
                        level=level,
                        component="guardian",
                        message=msg,
                        profile=profile,
                        detail={"check": name, "tier": tier},
                        fixed=fixed,
                    )
                    results["checks"].append({"name": name, "level": level, "message": msg})
                except Exception as exc:
                    guardian_store.log_event(
                        conn,
                        level="ERROR",
                        component="guardian",
                        message=str(exc),
                        profile=profile,
                        detail={"check": name},
                    )
                    results["checks"].append({"name": name, "level": "ERROR", "message": str(exc)})
            results["status"] = guardian_store.latest_status(conn)
        finally:
            conn.close()
        self.on_status(f"Guardian {profile} done — {results.get('status', 'green')}")
        return results

    def _check_venv(self) -> tuple[str, str]:
        venv_py = self.base_dir / ".venv" / "Scripts" / "python.exe"
        if venv_py.is_file():
            return "INFO", "Virtual environment OK"
        return "WARN", "Missing .venv — run Install / Update"

    def _check_folders(self) -> tuple[str, str]:
        for name in ("data", "logs", "exports"):
            p = self.base_dir / name
            if not p.is_dir():
                p.mkdir(parents=True, exist_ok=True)
        return "INFO", "Program folders OK"

    def _check_host(self) -> tuple[str, str]:
        try:
            import urllib.request

            port = 8765
            settings = self.base_dir / "data" / "local_host_settings.json"
            if settings.is_file():
                import json

                port = int(json.loads(settings.read_text(encoding="utf-8")).get("port", 8765))
            req = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
            if req.status == 200:
                return "INFO", f"Host responding on port {port}"
        except Exception:
            pass
        return "INFO", "Host not running (optional unless sharing mobile access)"

    def _check_deps(self) -> tuple[str, str]:
        try:
            import flask  # noqa: F401

            return "INFO", "Core dependencies import OK"
        except Exception as exc:
            return "WARN", f"Dependency check: {exc}"

    def _check_consistency(self) -> tuple[str, str]:
        from app.reliability.consistency_audit import run_read_only_audit

        rep = run_read_only_audit(self.base_dir)
        n = len(rep.get("issues") or [])
        if n:
            return "WARN", f"Consistency audit: {n} issue(s)"
        return "INFO", "Consistency audit OK"


def get_scheduler(base_dir=None) -> GuardianScheduler:
    global _scheduler
    with _lock:
        if _scheduler is None:
            _scheduler = GuardianScheduler(base_dir=base_dir)
        return _scheduler
