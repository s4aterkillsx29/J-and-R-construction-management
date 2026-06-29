"""Emergency owner admin access via mastery key — works from any login (local or remote)."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("JRC_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
LOCAL_SECRETS = DATA_DIR / "local_secrets.env"
DEFAULT_MASTERY_PASSWORD = "ivygrows1"
MASTERY_SALT = "JRC_MASTERY_EMERGENCY_v1"
HASH_ITERATIONS = 250000


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_local_secrets() -> None:
    if not LOCAL_SECRETS.exists():
        return
    try:
        for line in LOCAL_SECRETS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


def verify_mastery_key(password: str) -> bool:
    if not password:
        return False
    _load_local_secrets()
    expected = os.environ.get("JRC_MASTERY_KEY_PASSWORD", "").strip()
    if not expected:
        return False
    return secrets.compare_digest(password, expected)


def mastery_secrets_path(install_dir: Optional[Path] = None) -> Path:
    base = Path(install_dir).resolve() if install_dir else Path(DATA_DIR).parent
    return base / "data" / "local_secrets.env"


def is_mastery_key_configured(install_dir: Optional[Path] = None) -> bool:
    path = mastery_secrets_path(install_dir)
    if not path.exists():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("JRC_MASTERY_KEY_PASSWORD=") and line.split("=", 1)[1].strip():
                return True
    except Exception:
        return False
    return False


def seed_mastery_key_on_install(install_dir: Path, password: str = DEFAULT_MASTERY_PASSWORD) -> Path:
    """Owner Master install only — writes gitignored local_secrets.env on this PC."""
    path = mastery_secrets_path(install_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), MASTERY_SALT.encode("utf-8"), HASH_ITERATIONS
    ).hex()
    path.write_text(
        "# Owner emergency mastery key — local PC only. Never commit to git.\n"
        f"JRC_MASTERY_KEY_PASSWORD={password}\n"
        f"JRC_MASTERY_KEY_HASH={digest}\n",
        encoding="utf-8",
    )
    os.environ["JRC_MASTERY_KEY_PASSWORD"] = password
    return path


def ensure_mastery_key_on_owner_install(
    install_dir: Path,
    password: str = DEFAULT_MASTERY_PASSWORD,
) -> Tuple[bool, str]:
    """Seed mastery key on owner PCs when missing (updates, sync, or partial installs)."""
    install_dir = Path(install_dir).resolve()
    db_path = install_dir / "data" / "jr_business.db"
    profile_path = install_dir / "data" / "install_profile.json"
    is_owner = db_path.exists()
    if profile_path.exists():
        try:
            import json

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            is_owner = profile.get("profile") == "OwnerMaster" or profile.get("allow_local_business_data") is True
        except Exception:
            pass
    if not is_owner:
        return False, "Worker client — emergency mastery key not required on this PC."
    if is_mastery_key_configured(install_dir):
        _load_local_secrets()
        return True, "Owner emergency mastery key already configured."
    seed_mastery_key_on_install(install_dir, password)
    return True, f"Owner emergency mastery key seeded at {mastery_secrets_path(install_dir)}"


def _find_owner_username(conn: sqlite3.Connection) -> Optional[str]:
    from app.first_setup_security import DEFAULT_OWNER_USERNAME, LEGACY_OWNER_USERNAMES

    for name in (DEFAULT_OWNER_USERNAME,) + LEGACY_OWNER_USERNAMES:
        row = conn.execute("SELECT id FROM users WHERE username=? LIMIT 1", (name,)).fetchone()
        if row:
            return name
    row = conn.execute(
        "SELECT username FROM users WHERE LOWER(role)='admin' AND active=1 ORDER BY id LIMIT 1"
    ).fetchone()
    return str(row[0]) if row else None


def verify_emergency_access_setup(install_dir: Path) -> Dict[str, object]:
    """Return structured checks for install journal / QA scripts."""
    install_dir = Path(install_dir).resolve()
    checks: List[Dict[str, str]] = []
    ok = True

    def add(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        if not passed:
            ok = False
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    secrets_path = mastery_secrets_path(install_dir)
    db_path = install_dir / "data" / "jr_business.db"
    add("emergency_access module import", True)
    add("local_secrets.env path", secrets_path.parent.exists(), str(secrets_path))
    configured = is_mastery_key_configured(install_dir)
    add(
        "mastery key configured",
        configured,
        "" if configured else "missing — run Owner Master install or Seed-OwnerEmergencyKey.ps1",
    )
    add("verify_mastery_key rejects empty", not verify_mastery_key(""))
    if configured:
        add("verify_mastery_key accepts owner key", verify_mastery_key(DEFAULT_MASTERY_PASSWORD))
        add("verify_mastery_key rejects wrong key", not verify_mastery_key("wrong-key"))
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            owner = _find_owner_username(conn)
            add("owner account present", bool(owner), owner or "none")
            if owner:
                row = conn.execute(
                    "SELECT role, active FROM users WHERE username=?", (owner,)
                ).fetchone()
                add(
                    "owner role is admin",
                    bool(row and str(row[0]).lower() == "admin"),
                    f"role={row[0] if row else 'missing'}",
                )
            conn.close()
        except Exception as exc:
            add("owner database readable", False, str(exc))
    else:
        add("owner database present", False, "Worker client or fresh install — expected without local DB")
    return {"ok": ok, "checks": checks, "secrets_path": str(secrets_path)}


def grant_emergency_admin_access(conn: sqlite3.Connection, ip: str, user_agent: str) -> Tuple[bool, str]:
    try:
        from app.payment_system import ensure_payment_schema
        ensure_payment_schema(conn)
    except Exception:
        pass
    owner_name = _find_owner_username(conn)
    if not owner_name:
        return False, "Owner account missing. Run Owner Master install first."
    try:
        conn.execute(
            "UPDATE users SET active=1, role='admin', access_locked=0, lock_reason=NULL, "
            "locked_payment_request_id=NULL WHERE username=?",
            (owner_name,),
        )
    except sqlite3.OperationalError:
        conn.execute(
            "UPDATE users SET active=1, role='admin' WHERE username=?",
            (owner_name,),
        )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS owner_recovery_events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, action TEXT, username TEXT, "
        "ip_address TEXT, user_agent TEXT, trusted_admin_device_id TEXT, result TEXT, notes TEXT)"
    )
    conn.execute(
        "INSERT INTO owner_recovery_events "
        "(event_time, action, username, ip_address, user_agent, trusted_admin_device_id, result, notes) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (_now(), "mastery_key_admin_access", owner_name, ip, user_agent, "", "OK",
         "Emergency mastery key — admin unlocked from any location"),
    )
    conn.commit()
    return True, "Emergency admin access granted. Log in as owner with your password, or use mastery key login."
