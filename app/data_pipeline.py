"""
Data pipeline routing — where business data, sessions, and memory live.

MASTER_LOCAL (Jacob owner PC):
  - Full jr_business.db, evidence, exports, backups on this machine
  - Session archives + state memory + live backup folders on this PC
  - Source of truth for office work (Dropbox + local install)

WORKER_CLIENT (other users' PCs):
  - App shell only — NO business database or files without admin permission
  - Must use host/cloud URL in browser

CLOUD_HOST (Render/Railway/Docker):
  - Persistent JRC_DATA_DIR on server volume — separate from master PC
  - Remote users connect here; master PC keeps its own full local copy
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]

MODE_MASTER = "MASTER_LOCAL"
MODE_WORKER = "WORKER_CLIENT"
MODE_CLOUD = "CLOUD_HOST"
MODE_DEDICATED = "DEDICATED_HOST"
MODE_STANDARD = "STANDARD_LOCAL"


@dataclass
class ResolvedPaths:
    base_dir: Path
    data_dir: Path
    db_path: Path
    export_dir: Path
    evidence_dir: Path
    backup_dir: Path
    chatgpt_imports_dir: Path
    sessions_archive_dir: Path
    state_memory_dir: Path
    live_backup_dir: Path
    pipeline_manifest_path: Path
    mode: str
    data_authority: str
    business_storage_enabled: bool
    remote_host_required: bool
    cloud_data_dir: bool


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_cloud_deployment() -> bool:
    if os.environ.get("JRC_CLOUD_PRIMARY_MODE", "0") == "1":
        return True
    data_dir = os.environ.get("JRC_DATA_DIR", "").strip()
    if not data_dir:
        return False
    try:
        return Path(data_dir).resolve() != (BASE_DIR / "data").resolve()
    except Exception:
        return bool(data_dir and data_dir not in (str(BASE_DIR / "data"), "data"))


def get_install_profile() -> Dict[str, Any]:
    for candidate in (
        Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser() / "install_profile.json",
        BASE_DIR / "data" / "install_profile.json",
    ):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def get_data_mode() -> str:
    if is_cloud_deployment():
        return MODE_CLOUD
    profile = get_install_profile()
    if profile.get("profile") == "WorkerClient" or profile.get("allow_local_business_data") is False:
        return MODE_WORKER
    if profile.get("profile") == "OwnerMaster":
        return MODE_MASTER
    if profile.get("profile") == "DedicatedHost":
        return MODE_DEDICATED
    try:
        from app.master_owner import is_master_owner_device
        if is_master_owner_device():
            return MODE_MASTER
    except Exception:
        pass
    return MODE_STANDARD


def get_data_authority(mode: str) -> str:
    if mode == MODE_CLOUD:
        return "cloud_volume"
    if mode == MODE_DEDICATED:
        return "dedicated_host_pc"
    if mode == MODE_WORKER:
        return "remote_host"
    return "master_pc"


def resolve_paths() -> ResolvedPaths:
    mode = get_data_mode()
    cloud = mode == MODE_CLOUD
    data_dir = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
    db_path = Path(os.environ.get("JRC_DB_PATH", str(data_dir / "jr_business.db"))).expanduser()
    export_dir = Path(os.environ.get("JRC_EXPORT_DIR", str(BASE_DIR / "exports" if not cloud else data_dir.parent / "exports"))).expanduser()
    if cloud:
        export_dir = Path(os.environ.get("JRC_EXPORT_DIR", str(Path(os.environ.get("JRC_DATA_DIR", "/var/data/jrc")) / "exports"))).expanduser()
    evidence_dir = Path(os.environ.get("JRC_EVIDENCE_DIR", str(BASE_DIR / "evidence"))).expanduser()
    backup_dir = Path(os.environ.get("JRC_BACKUP_DIR", str(BASE_DIR / "backups"))).expanduser()
    chatgpt_dir = Path(os.environ.get("JRC_CHATGPT_IMPORTS_DIR", str(BASE_DIR / "chatgpt_imports"))).expanduser()
    if cloud:
        root = data_dir.parent if data_dir.name == "data" else data_dir
        export_dir = Path(os.environ.get("JRC_EXPORT_DIR", str(root / "exports"))).expanduser()
        evidence_dir = Path(os.environ.get("JRC_EVIDENCE_DIR", str(root / "evidence"))).expanduser()
        backup_dir = Path(os.environ.get("JRC_BACKUP_DIR", str(root / "backups"))).expanduser()
        chatgpt_dir = Path(os.environ.get("JRC_CHATGPT_IMPORTS_DIR", str(root / "chatgpt_imports"))).expanduser()

    sessions_archive = data_dir / "sessions_archive"
    state_memory = data_dir / "state_memory"
    live_backup = data_dir / "live_backup"
    manifest = data_dir / "pipeline_manifest.json"
    worker = mode == MODE_WORKER
    master_or_cloud = mode in (MODE_MASTER, MODE_CLOUD, MODE_STANDARD, MODE_DEDICATED)

    return ResolvedPaths(
        base_dir=BASE_DIR,
        data_dir=data_dir,
        db_path=db_path,
        export_dir=export_dir,
        evidence_dir=evidence_dir,
        backup_dir=backup_dir,
        chatgpt_imports_dir=chatgpt_dir,
        sessions_archive_dir=sessions_archive,
        state_memory_dir=state_memory,
        live_backup_dir=live_backup,
        pipeline_manifest_path=manifest,
        mode=mode,
        data_authority=get_data_authority(mode),
        business_storage_enabled=not worker,
        remote_host_required=worker,
        cloud_data_dir=cloud,
    )


def business_data_allowed_locally() -> bool:
    return resolve_paths().business_storage_enabled


def mode_label() -> str:
    p = resolve_paths()
    labels = {
        MODE_MASTER: "Master Owner PC — full local storage & backup hub",
        MODE_WORKER: "Worker Client — remote/cloud only (no local business files)",
        MODE_CLOUD: "Cloud Host — persistent server volume",
        MODE_DEDICATED: "Dedicated Host Laptop — 24/7 LAN server on this PC",
        MODE_STANDARD: "Standard Local — business data on this PC",
    }
    return labels.get(p.mode, p.mode)


def require_master_local_storage() -> None:
    """Block Office app on worker clients that must not store business data."""
    import sys
    import tkinter as tk
    from tkinter import messagebox

    p = resolve_paths()
    if p.business_storage_enabled:
        return
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Remote Client Install",
        "This PC is a Worker/Remote Client.\n\n"
        "Business data is NOT stored on this machine.\n"
        "Use Mobile Links or Cloud Access from Start Center to connect.\n\n"
        "Only the Owner Master PC keeps live database, sessions, and backups.",
        parent=root,
    )
    root.destroy()
    raise SystemExit(0)


def assert_office_app_allowed() -> Tuple[bool, str]:
    p = resolve_paths()
    if p.business_storage_enabled:
        return True, mode_label()
    return False, (
        "Worker/Remote Client: Office app requires the Owner Master PC. "
        "Use the web dashboard via host or cloud URL."
    )


def ensure_master_storage_layout() -> ResolvedPaths:
    """Create master-only folders for sessions, state memory, and rolling backups."""
    p = resolve_paths()
    if not p.business_storage_enabled:
        return p
    for folder in (
        p.data_dir,
        p.export_dir,
        p.evidence_dir,
        p.backup_dir,
        p.chatgpt_imports_dir,
        p.sessions_archive_dir,
        p.state_memory_dir,
        p.live_backup_dir,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    write_pipeline_manifest(p)
    return p


def write_pipeline_manifest(paths: Optional[ResolvedPaths] = None) -> Path:
    p = paths or resolve_paths()
    cloud_url = ""
    try:
        cc = BASE_DIR / "data" / "cloud_connect.json"
        if cc.exists():
            cloud_url = json.loads(cc.read_text(encoding="utf-8")).get("cloud_base_url", "")
    except Exception:
        pass
    payload = {
        "updated_at": _now(),
        "mode": p.mode,
        "data_authority": p.data_authority,
        "business_storage_enabled": p.business_storage_enabled,
        "remote_host_required": p.remote_host_required,
        "cloud_data_dir": p.cloud_data_dir,
        "paths": {
            "data_dir": str(p.data_dir),
            "db_path": str(p.db_path),
            "export_dir": str(p.export_dir),
            "evidence_dir": str(p.evidence_dir),
            "backup_dir": str(p.backup_dir),
            "sessions_archive_dir": str(p.sessions_archive_dir),
            "state_memory_dir": str(p.state_memory_dir),
            "live_backup_dir": str(p.live_backup_dir),
        },
        "cloud_mirror_url": cloud_url,
        "routing_notes": {
            MODE_MASTER: "All server sessions, database, and memory snapshots stay on this owner PC.",
            MODE_WORKER: "No business DB on disk. Connect via LAN host or cloud URL only.",
            MODE_CLOUD: "Server uses JRC_DATA_DIR volume. Master PC keeps separate local copy for office.",
            MODE_DEDICATED: "Dedicated home laptop runs the LAN host 24/7. Office laptop connects via browser.",
        }.get(p.mode, ""),
    }
    p.pipeline_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    p.pipeline_manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p.pipeline_manifest_path


def snapshot_sessions(conn: sqlite3.Connection, paths: Optional[ResolvedPaths] = None) -> Optional[Path]:
    """Archive active sessions to disk on master/cloud (not worker clients)."""
    p = paths or resolve_paths()
    if not p.business_storage_enabled:
        return None
    p.sessions_archive_dir.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        "SELECT session_id, user_id, username, role, ip_address, login_time, last_seen, active, revoked "
        "FROM online_sessions ORDER BY last_seen DESC"
    ).fetchall()
    data = [dict(r) for r in rows]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = p.sessions_archive_dir / f"sessions_{stamp}.json"
    latest = p.sessions_archive_dir / "latest_sessions.json"
    payload = {"archived_at": _now(), "mode": p.mode, "count": len(data), "sessions": data}
    text = json.dumps(payload, indent=2)
    out.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    # Keep last 50 archives
    archives = sorted(p.sessions_archive_dir.glob("sessions_*.json"), reverse=True)
    for old in archives[50:]:
        try:
            old.unlink()
        except Exception:
            pass
    return out


def snapshot_runtime_state(paths: Optional[ResolvedPaths] = None) -> Optional[Path]:
    """Save ports, cloud URL, install profile into state memory."""
    p = paths or resolve_paths()
    if not p.business_storage_enabled:
        return None
    p.state_memory_dir.mkdir(parents=True, exist_ok=True)
    state: Dict[str, Any] = {"saved_at": _now(), "mode": p.mode}
    for name, rel in (
        ("local_host_settings", "data/local_host_settings.json"),
        ("cloud_connect", "data/cloud_connect.json"),
        ("install_profile", "data/install_profile.json"),
        ("installer_source", "INSTALLER_SOURCE.txt"),
    ):
        fp = BASE_DIR / rel
        if fp.exists():
            try:
                state[name] = json.loads(fp.read_text(encoding="utf-8")) if fp.suffix == ".json" else fp.read_text(encoding="utf-8").strip()
            except Exception:
                state[name] = "(unreadable)"
    out = p.state_memory_dir / "runtime_state.json"
    out.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return out


def run_live_backup(paths: Optional[ResolvedPaths] = None) -> Optional[Path]:
    """Rolling quick backup of database into data/live_backup on master PC."""
    p = paths or resolve_paths()
    if not p.business_storage_enabled or not p.db_path.exists():
        return None
    p.live_backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = p.live_backup_dir / f"jr_business_live_{stamp}.db"
    shutil.copy2(p.db_path, dest)
    wal = Path(str(p.db_path) + "-wal")
    if wal.exists():
        shutil.copy2(wal, p.live_backup_dir / f"jr_business_live_{stamp}.db-wal")
    archives = sorted(p.live_backup_dir.glob("jr_business_live_*.db"), reverse=True)
    for old in archives[20:]:
        try:
            old.unlink()
            w = Path(str(old) + "-wal")
            if w.exists():
                w.unlink()
        except Exception:
            pass
    return dest


def run_master_pipeline_maintenance(db_path: Optional[Path] = None) -> List[str]:
    """Full pipeline pass: layout, manifest, sessions, state, live backup."""
    results: List[str] = []
    p = ensure_master_storage_layout()
    results.append(f"Mode: {p.mode} — {mode_label()}")
    results.append(f"Manifest: {write_pipeline_manifest(p)}")
    db = db_path or p.db_path
    if db.exists():
        try:
            with sqlite3.connect(db) as conn:
                conn.row_factory = sqlite3.Row
                snap = snapshot_sessions(conn, p)
                if snap:
                    results.append(f"Sessions archived: {snap}")
        except Exception as exc:
            results.append(f"Session archive warning: {exc}")
    st = snapshot_runtime_state(p)
    if st:
        results.append(f"State memory: {st}")
    lb = run_live_backup(p)
    if lb:
        results.append(f"Live DB backup: {lb}")
    if db.exists():
        try:
            with sqlite3.connect(db) as conn:
                conn.row_factory = sqlite3.Row
                from app.dropbox_business import ensure_dropbox_file_source, sync_backup_to_dropbox
                ensure_dropbox_file_source(conn)
                ok, msg, _ = sync_backup_to_dropbox(conn, BASE_DIR)
                results.append(msg if ok else f"Dropbox backup: {msg}")
        except Exception as exc:
            results.append(f"Dropbox sync warning: {exc}")
    return results


def verify_pipelines() -> List[Tuple[str, str, str]]:
    """Returns list of (level, component, message) for system check / troubleshooter."""
    results: List[Tuple[str, str, str]] = []
    p = resolve_paths()
    results.append(("INFO", "Data Mode", f"{p.mode} — {mode_label()}"))
    results.append(("INFO", "Data Authority", p.data_authority))
    if p.mode == MODE_WORKER:
        if p.db_path.exists():
            results.append(("WARN", "Worker Client", f"Business database should not exist: {p.db_path}"))
        else:
            results.append(("OK", "Worker Client", "No local business database (correct)."))
        results.append(("INFO", "Worker Client", "Use host/cloud URL — no local business storage."))
    elif p.mode == MODE_MASTER:
        for label, path in [
            ("Database", p.db_path),
            ("Sessions archive", p.sessions_archive_dir),
            ("State memory", p.state_memory_dir),
            ("Live backup", p.live_backup_dir),
        ]:
            if path.suffix == ".db":
                ok = path.exists()
            else:
                ok = path.is_dir()
            results.append(("OK" if ok else "WARN", "Master Storage", f"{label}: {'ready' if ok else 'missing — run pipeline maintenance'}"))
        if p.pipeline_manifest_path.exists():
            results.append(("OK", "Pipeline Manifest", str(p.pipeline_manifest_path)))
        else:
            results.append(("WARN", "Pipeline Manifest", "Not written yet — run pipeline maintenance"))
    elif p.mode == MODE_CLOUD:
        results.append(("INFO", "Cloud Host", f"Data on server volume: {p.data_dir}"))
        results.append(("INFO", "Cloud Host", "Master PC keeps separate local copy for Jacob office work."))
    elif p.mode == MODE_DEDICATED:
        for label, path in [
            ("Database", p.db_path),
            ("Sessions archive", p.sessions_archive_dir),
            ("State memory", p.state_memory_dir),
            ("Live backup", p.live_backup_dir),
        ]:
            ok = path.exists() if path.suffix == ".db" else path.is_dir()
            results.append(("OK" if ok else "WARN", "Dedicated Host", f"{label}: {'ready' if ok else 'missing'}"))
        results.append(("INFO", "Dedicated Host", "Local login on this PC: jrc_host (host operator). Owner ivygrows from office browser."))
    if p.cloud_data_dir:
        results.append(("OK", "Cloud Sourcing", f"JRC_DATA_DIR active: {p.data_dir}"))
    else:
        cc = BASE_DIR / "data" / "cloud_connect.json"
        if cc.exists():
            results.append(("INFO", "Cloud Link", "Cloud URL configured — remote users use cloud; master PC uses local DB."))
    return results
