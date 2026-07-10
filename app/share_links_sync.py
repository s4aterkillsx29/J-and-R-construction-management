"""
Refresh guest share links, cloud_connect.json, and Dropbox program docs after every live update.

Writes:
  - data/cloud_connect.json on each live install
  - dropbox .../07_JRC_MANAGER_PROGRAM_FILES/JRC_MANAGER_SHARE_LINKS_LATEST.txt
  - dropbox .../00_START_HERE/READABLE/JRC_MANAGER_SHARE_LINKS.txt
  - dated snapshot .../YYYY-MM-DD__JRC-ADM__Share_Links_Auto.txt
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8765
GITHUB_REPO = "https://github.com/s4aterkillsx29/J-and-R-construction-management"

PROFILE_CANDIDATES = (
    Path(os.environ.get("JRC_HOST_PROFILE", "")),
    Path.home() / "projects" / "HOST-PC-ADMIN" / "config" / "host-control-profile.json",
    Path(r"c:\Users\enrag\projects\HOST-PC-ADMIN\config\host-control-profile.json"),
    Path(r"c:\Users\enrag\projects\JRC-Construction-Office\tools\host-control-profile.example.json"),
)

DROPBOX_CANDIDATES = (
    Path(os.environ.get("JRC_DROPBOX_RECORDS", "")),
    Path(r"c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records"),
    Path(
        r"c:\Users\enrag\Dropbox\All Files"
        r"\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
        r"\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"
    ),
)


def _load_profile() -> Dict[str, str]:
    defaults = {
        "host_lan_ip": "192.168.50.71",
        "host_tailscale_ip": "100.74.112.42",
        "host_pc_name": "jrcmanagerhost",
        "host_tailscale_name": "jrcmanagerhost",
        "host_magic_dns": "jrcmanagerhost.tail01d49e.ts.net",
        "office_lan_ip": "192.168.50.59",
        "office_tailscale_ip": "100.95.109.11",
        "office_pc_name": "JRCONST",
    }
    for path in PROFILE_CANDIDATES:
        if not path or not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            for key in defaults:
                val = (loaded.get(key) or "").strip()
                if val:
                    defaults[key] = val
            defaults["_profile_path"] = str(path)
            return defaults
        except Exception:
            continue
    defaults["_profile_path"] = ""
    return defaults


def _http_json(url: str, timeout: float = 3.0) -> Tuple[bool, Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JRC-ShareLinksSync/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, json.loads(body) if body.strip().startswith("{") else {"raw": body[:200]}
    except Exception as exc:
        return False, {"error": str(exc)}


def _live_install_dirs() -> List[Path]:
    paths: List[Path] = []
    env = os.environ.get("JRC_LIVE_DIR", "").strip()
    if env:
        paths.append(Path(env))
    paths.append(Path(os.path.expandvars(r"%LOCALAPPDATA%\J_and_R_Construction_Manager")))
    paths.append(BASE_DIR)
    for desk in (
        Path.home() / "Desktop" / "J and R Construction Manager",
        Path.home() / "OneDrive" / "Desktop" / "J and R Construction Manager",
        Path.home() / "Documents" / "JRC" / "J-and-R-construction-management",
    ):
        paths.append(desk)
    seen: set[str] = set()
    out: List[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen and p.exists():
            seen.add(key)
            out.append(p)
    return out


def _dropbox_root() -> Optional[Path]:
    for p in DROPBOX_CANDIDATES:
        if p and p.is_dir() and (p / "00_START_HERE").is_dir():
            return p
    return None


def _version_from_repo() -> str:
    vf = BASE_DIR / "VERSION.txt"
    if vf.is_file():
        return vf.read_text(encoding="utf-8").strip() or "unknown"
    return "unknown"


def _git_head() -> str:
    git_dir = BASE_DIR / ".git"
    if not git_dir.is_dir():
        return ""
    head = git_dir / "HEAD"
    if not head.is_file():
        return ""
    ref = head.read_text(encoding="utf-8").strip()
    if ref.startswith("ref: "):
        ref_path = git_dir / ref[5:].strip()
        if ref_path.is_file():
            return ref_path.read_text(encoding="utf-8").strip()[:12]
    return ref[:12]


def _host_short_name(profile: Dict[str, str]) -> str:
    return (profile.get("host_tailscale_name") or profile.get("host_pc_name") or "jrcmanagerhost").strip()


def _typing_block(ip: str, port: int = DEFAULT_PORT, slug: str = "go") -> List[str]:
    """Human-friendly lines for typing the share URL on a phone."""
    if not ip:
        return []
    typed = f"{ip}:{port}/{slug}"
    octets = ip.split(".")
    say_ip = " dot ".join(octets)
    port_digits = " ".join(str(port))
    lines = [
        f"  Type exactly:  {typed}",
        f"  Say out loud:  {say_ip}  colon  {port_digits}  slash  {slug}",
    ]
    if len(octets) == 4:
        lines.append(
            f"  Chunked:       {octets[0]}.{octets[1]}  ·  {octets[2]}.{octets[3]}  :  {port}  /  {slug}"
        )
    return lines


def build_urls(profile: Dict[str, str], port: int = DEFAULT_PORT) -> Dict[str, str]:
    ts_ip = profile.get("host_tailscale_ip", "")
    lan_ip = profile.get("host_lan_ip", "")
    magic = profile.get("host_magic_dns", "").strip()
    if not magic and profile.get("host_tailscale_name"):
        magic = f"{profile['host_tailscale_name']}.tail01d49e.ts.net"

    def base(ip_or_host: str) -> str:
        host = ip_or_host.strip()
        if not host:
            return ""
        if not host.startswith("http"):
            host = f"http://{host}:{port}"
        return host.rstrip("/")

    ts_base = base(ts_ip)
    lan_base = base(lan_ip)
    magic_base = base(magic) if magic else ""
    host_name = _host_short_name(profile)
    host_base = f"http://{host_name}:{port}" if host_name else ""

    urls = {
        "cloud_base_url": ts_base,
        "tailscale_url": ts_base,
        "lan_url": lan_base,
        "magic_dns": magic_base,
        "host_name": host_name,
        "host_name_url": f"{host_base}/goJandRconstruction" if host_base else "",
        "connect_url": f"{ts_base}/connect" if ts_base else "",
        "branded_url": f"{ts_base}/goJandRconstruction" if ts_base else "",
        "branded_slug": "goJandRconstruction",
        "mobile_url": f"{ts_base}/mobile" if ts_base else "",
        "mobile_messages_url": f"{ts_base}/mobile/messages" if ts_base else "",
        "register_url": f"{ts_base}/register" if ts_base else "",
        "login_url": f"{ts_base}/login" if ts_base else "",
        "connect_lan": f"{lan_base}/connect" if lan_base else "",
        "branded_lan": f"{lan_base}/goJandRconstruction" if lan_base else "",
        "connect_magic": f"{magic_base}/connect" if magic_base else "",
        "branded_magic": f"{magic_base}/goJandRconstruction" if magic_base else "",
        "github_repo": GITHUB_REPO,
        "tailscale_ip": ts_ip,
        "lan_ip": lan_ip,
    }
    return urls


def probe_host_health(profile: Dict[str, str], port: int = DEFAULT_PORT) -> Dict[str, Any]:
    ts_ip = profile.get("host_tailscale_ip", "")
    if not ts_ip:
        return {"ok": False, "error": "no host_tailscale_ip in profile"}
    url = f"http://{ts_ip}:{port}/api/health"
    ok, data = _http_json(url)
    result: Dict[str, Any] = {"ok": ok, "health_url": url}
    if ok:
        result.update(data)
        lan = (data.get("lan_ip") or data.get("lan_url") or "").strip()
        if lan:
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", lan)
            if m:
                result["detected_lan_ip"] = m.group(1)
    else:
        result["error"] = data.get("error", "health check failed")
    return result


def write_cloud_connect(install_dir: Path, urls: Dict[str, str], version: str) -> Path:
    data_dir = install_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "cloud_connect.json"
    payload = {
        "cloud_base_url": urls.get("cloud_base_url", ""),
        "tailscale_url": urls.get("tailscale_url", ""),
        "lan_url": urls.get("lan_url", ""),
        "connect_url": urls.get("connect_url", ""),
        "branded_url": urls.get("branded_url", ""),
        "host_name_url": urls.get("host_name_url", ""),
        "mobile_url": urls.get("mobile_url", ""),
        "mobile_messages_url": urls.get("mobile_messages_url", ""),
        "register_url": urls.get("register_url", ""),
        "magic_dns": urls.get("magic_dns", ""),
        "connect_magic": urls.get("connect_magic", ""),
        "connect_lan": urls.get("connect_lan", ""),
        "app_version": version,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "Auto-refreshed by share_links_sync on program update.",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _format_share_doc(
    urls: Dict[str, str],
    version: str,
    git_head: str,
    health: Dict[str, Any],
    profile_path: str,
) -> str:
    ts = time.strftime("%B %d, %Y %I:%M %p")
    date_slug = time.strftime("%Y-%m-%d")
    health_line = "OK" if health.get("ok") else f"UNREACHABLE — {health.get('error', 'unknown')}"
    host_ver = health.get("version") or health.get("app_version") or "(not probed)"
    git_line = f"{git_head}" if git_head else "(local only — not a git checkout)"
    ts_ip = urls.get("tailscale_ip", "")
    lan_ip = urls.get("lan_ip", "")
    host_name = urls.get("host_name", "")
    slug = urls.get("branded_slug", "go")

    lines = [
        "J & R CONSTRUCTION MANAGER — SHARE LINKS (auto-synced)",
        "Jacob Cosentino | J & R Construction",
        f"Date: {ts}",
        f"Version: {version}",
        f"GitHub: {GITHUB_REPO} @ {git_line}",
        f"Profile: {profile_path or '(defaults)'}",
        "",
        "=" * 78,
        "EASIEST TO TYPE (share this first)",
        "=" * 78,
    ]
    if host_name:
        lines.extend(
            [
                f"  By computer name (Tailscale — easiest, no IP digits):",
                f"    {host_name}:8765/{slug}",
                f"  Say:  {host_name}  colon  8 7 6 5  slash  {slug}",
                "",
            ]
        )
    if ts_ip:
        lines.append("  By Tailscale IP:")
        lines.extend(_typing_block(ts_ip, DEFAULT_PORT, slug))
        lines.append("")
    lines.extend(
        [
            "=" * 78,
            "COPY/PASTE FOR GUESTS (Tailscale on same tailnet)",
            "=" * 78,
            f"  Short link:",
            f"    {urls.get('branded_url', '')}",
            "",
            f"  By computer name:",
            f"    {urls.get('host_name_url', '')}",
            "",
            f"  Best link (connection + mobile bookmark):",
            f"    {urls.get('connect_url', '')}",
            "",
            f"  Mobile home (login required):",
            f"    {urls.get('mobile_url', '')}",
            "",
            f"  Live chat (after login):",
            f"    {urls.get('mobile_messages_url', '')}",
            "",
            f"  Request guest account:",
            f"    {urls.get('register_url', '')}",
            "",
            f"  MagicDNS (same tailnet):",
            f"    {urls.get('connect_magic', '')}",
            "",
            "=" * 78,
            "SAME Wi-Fi ONLY (at shop — no VPN needed)",
            "=" * 78,
        ]
    )
    if lan_ip:
        lines.append("  Type on phone (shop Wi-Fi):")
        lines.extend(_typing_block(lan_ip, DEFAULT_PORT, slug))
        lines.append("")
    lines.extend(
        [
            f"  {urls.get('connect_lan', '')}",
            f"  Short: {urls.get('branded_lan', '')}",
            "",
            "=" * 78,
            "HOST HEALTH (last probe)",
            "=" * 78,
            f"  Status: {health_line}",
            f"  Host reports version: {host_ver}",
            f"  Health URL: {health.get('health_url', '')}",
            "",
            "=" * 78,
            "GITHUB REPO (program source)",
            "=" * 78,
            f"  {GITHUB_REPO}",
            f"  Local commit: {git_line}",
            "",
            "DO NOT SHARE: owner passwords, emergency keys, RustDesk IDs.",
            "",
            f"Auto-generated {date_slug} by share_links_sync.py — updates on every program release.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_dropbox_share_docs(
    dropbox: Path,
    body: str,
) -> List[str]:
    notes: List[str] = []
    prog = dropbox / "07_JRC_MANAGER_PROGRAM_FILES"
    readable = dropbox / "00_START_HERE" / "READABLE"
    prog.mkdir(parents=True, exist_ok=True)
    readable.mkdir(parents=True, exist_ok=True)

    latest = prog / "JRC_MANAGER_SHARE_LINKS_LATEST.txt"
    latest.write_text(body, encoding="utf-8")
    notes.append(f"Wrote {latest}")

    dated = prog / f"{time.strftime('%Y-%m-%d')}__JRC-ADM__Share_Links_Auto.txt"
    dated.write_text(body, encoding="utf-8")
    notes.append(f"Wrote {dated}")

    read_copy = readable / "JRC_MANAGER_SHARE_LINKS.txt"
    read_copy.write_text(body, encoding="utf-8")
    notes.append(f"Wrote {read_copy}")

    # Keep Kaleb-named file in sync (same content, stable filename for dashboard pointer)
    kaleb = prog / "2026-07-08__JRC-ADM__Kaleb_Share_Links.txt"
    kaleb.write_text(body, encoding="utf-8")
    notes.append(f"Refreshed {kaleb.name}")

    easy = readable / "JRC_EASY_SHARE_LINK.txt"
    easy.write_text(body, encoding="utf-8")
    notes.append(f"Wrote {easy.name}")

    return notes


def _patch_dashboard_github(dropbox: Path, version: str, git_head: str) -> Optional[str]:
    dash = dropbox / "00_START_HERE" / "READABLE" / "BUSINESS_DASHBOARD.txt"
    if not dash.is_file():
        return None
    text = dash.read_text(encoding="utf-8")
    git_short = git_head or "HEAD"
    new_line = f"  GitHub: github.com/s4aterkillsx29/J-and-R-construction-management @ v{version} ({git_short})"
    new_share = "  Share link for guests: 07_JRC_MANAGER_PROGRAM_FILES/JRC_MANAGER_SHARE_LINKS_LATEST.txt"
    if re.search(r"^\s*GitHub:.*J-and-R-construction-management", text, re.M):
        text = re.sub(
            r"^\s*GitHub:.*J-and-R-construction-management.*$",
            new_line,
            text,
            count=1,
            flags=re.M,
        )
    if re.search(r"^\s*Share link for guests:", text, re.M):
        text = re.sub(
            r"^\s*Share link for guests:.*$",
            new_share,
            text,
            count=1,
            flags=re.M,
        )
    dash.write_text(text, encoding="utf-8")
    return str(dash)


def run_share_links_sync(
    *,
    probe: bool = True,
    write_dropbox: bool = True,
) -> Dict[str, Any]:
    from app.program_manifest import APP_VERSION

    profile = _load_profile()
    version = _version_from_repo() or APP_VERSION
    git_head = _git_head()
    health: Dict[str, Any] = {"ok": False, "skipped": not probe}
    if probe:
        health = probe_host_health(profile)
        detected = health.get("detected_lan_ip")
        if detected and detected != profile.get("host_lan_ip"):
            profile["host_lan_ip"] = detected

    urls = build_urls(profile)
    install_notes: List[str] = []
    for install in _live_install_dirs():
        try:
            p = write_cloud_connect(install, urls, version)
            install_notes.append(str(p))
        except Exception as exc:
            install_notes.append(f"FAIL {install}: {exc}")

    body = _format_share_doc(
        urls,
        version,
        git_head,
        health,
        profile.get("_profile_path", ""),
    )
    dropbox_notes: List[str] = []
    dropbox = _dropbox_root() if write_dropbox else None
    if dropbox:
        dropbox_notes = write_dropbox_share_docs(dropbox, body)
        patched = _patch_dashboard_github(dropbox, version, git_head)
        if patched:
            dropbox_notes.append(f"Patched dashboard GitHub line: {patched}")

    return {
        "version": version,
        "git_head": git_head,
        "urls": urls,
        "health": health,
        "profile_path": profile.get("_profile_path", ""),
        "cloud_connect_written": install_notes,
        "dropbox_written": dropbox_notes,
        "ok": bool(urls.get("connect_url")),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Refresh JRC share links and cloud_connect.json")
    parser.add_argument("--no-probe", action="store_true", help="Skip host health probe")
    parser.add_argument("--no-dropbox", action="store_true", help="Skip Dropbox doc writes")
    args = parser.parse_args()

    rep = run_share_links_sync(probe=not args.no_probe, write_dropbox=not args.no_dropbox)
    print(json.dumps(rep, indent=2))
    if not rep.get("ok"):
        return 1
    if rep.get("health", {}).get("ok") is False and not args.no_probe:
        print("WARNING: host health probe failed — links written from profile anyway")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
