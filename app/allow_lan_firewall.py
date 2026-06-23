"""Allow inbound LAN access to the JRC shared host through Windows Firewall."""
from __future__ import annotations

import sys

from app.runtime_utils import ensure_lan_firewall, lan_firewall_rule_exists, lan_firewall_port_range


def main() -> int:
    low, high = lan_firewall_port_range()
    print("J and R Construction Manager — LAN Firewall Setup")
    print(f"Opening TCP ports {low}-{high} for trusted private Wi-Fi/VPN.")
    print()
    if lan_firewall_rule_exists():
        print(f"OK: Firewall rule already exists for ports {low}-{high}.")
        return 0
    ok, msg = ensure_lan_firewall()
    print(msg)
    if ok:
        print()
        print("Phones on the same Wi-Fi can now reach the shared host.")
        print("Restart the local host if it was already running, then test:")
        print("  http://YOUR-LAN-IP:PORT/connect")
        return 0
    print()
    print("Run this script as Administrator (right-click ALLOW_LAN_FIREWALL_ACCESS.bat).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
