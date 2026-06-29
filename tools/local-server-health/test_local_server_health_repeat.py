"""Repeat smoke tests for J&R Construction Manager Local Server Health.

Run from the repository root:

    python tools/local-server-health/test_local_server_health_repeat.py

This intentionally tests the same endpoints used by the Windows no-console health tool.
"""

from __future__ import annotations

import importlib.util
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "tools" / "local-server-health" / "app" / "JRC_Local_Server_Health.pyw"
DEFAULT_PORT = 8765
BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}"

ENDPOINTS = [
    ("login", "/login", 200, "Login page test passed"),
    ("root", "/", 200, "Login page test passed"),
    ("api_health", "/api/health", 200, '"status": "healthy"'),
    ("mobile_ping", "/api/mobile/ping", 200, '"mobile_ping": "passed"'),
    ("lan_phone_test", "/api/lan/phone-test", 200, '"lan_phone_test": "passed"'),
    ("not_found", "/does-not-exist", 404, '"error": "not_found"'),
]


def load_health_module():
    if not APP_PATH.exists():
        raise FileNotFoundError(f"Health app not found: {APP_PATH}")
    spec = importlib.util.spec_from_file_location("jrc_local_server_health", APP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec from {APP_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def http_get(path: str, timeout: float = 3.0) -> tuple[int, str, str]:
    url = BASE_URL + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(1200).decode("utf-8", errors="replace")
            return response.status, response.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as exc:
        body = exc.read(1200).decode("utf-8", errors="replace")
        return exc.code, exc.headers.get("Content-Type", ""), body


def main() -> int:
    health = load_health_module()
    failures: list[tuple[object, ...]] = []

    for cycle in range(1, 6):
        start_msg = health.start_health_server(DEFAULT_PORT)
        print(f"cycle={cycle} start={start_msg}")

        if cycle == 1:
            double_start_msg = health.start_health_server(DEFAULT_PORT)
            print(f"cycle={cycle} double_start={double_start_msg}")
            if "already running" not in double_start_msg:
                failures.append((cycle, "double_start", double_start_msg))

        time.sleep(0.25)

        for name, path, expected_status, expected_text in ENDPOINTS:
            status, content_type, body = http_get(path)
            contains = expected_text in body
            print(f"cycle={cycle} endpoint={name} status={status} contains={contains} content_type={content_type}")
            if status != expected_status or not contains:
                failures.append((cycle, name, status, body[:200]))

        stop_msg = health.stop_health_server()
        print(f"cycle={cycle} stop={stop_msg}")
        if "stopped" not in stop_msg:
            failures.append((cycle, "stop", stop_msg))
        time.sleep(0.15)

    try:
        urllib.request.urlopen(BASE_URL + "/api/health", timeout=1.0)
        failures.append(("after_stop", "server still answered"))
    except Exception as exc:  # expected after shutdown
        print(f"after_stop_expected_failure={type(exc).__name__}")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("ALL_LOCALHOST_HEALTH_TESTS_PASSED cycles=5 endpoints_per_cycle=6 total_endpoint_checks=30")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
