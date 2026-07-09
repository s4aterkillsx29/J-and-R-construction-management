# -*- coding: utf-8 -*-
"""Verify web dashboard shows role tiles after login."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


def main() -> int:
    os.environ.setdefault("JRC_SKIP_STARTUP_REPAIR", "1")
    td = tempfile.mkdtemp()
    base = Path(td)
    for d in ("data", "exports", "evidence", "chatgpt_imports", "backups"):
        (base / d).mkdir()
    env = {
        "JRC_DATA_DIR": str(base / "data"),
        "JRC_EXPORT_DIR": str(base / "exports"),
        "JRC_EVIDENCE_DIR": str(base / "evidence"),
        "JRC_CHATGPT_IMPORTS_DIR": str(base / "chatgpt_imports"),
        "JRC_BACKUP_DIR": str(base / "backups"),
        "JRC_DB_PATH": str(base / "data" / "jr_business.db"),
        "JRC_PORT": "8765",
        "JRC_ALLOW_LOCAL_DEFAULT_ADMIN": "1",
    }
    for k, v in env.items():
        os.environ[k] = v
    import importlib
    import sitecustomize

    sitecustomize._repair()
    ns = importlib.import_module("app.network_server")
    ns = importlib.reload(ns)
    ns.init_db()
    with ns.direct_db() as conn:
        salt, ph = ns.hash_password("TestPass123!")
        conn.execute(
            "INSERT OR REPLACE INTO users (id,username,display_name,role,salt,password_hash,active,must_change_password,created_at,notes,owner_account) "
            "VALUES (1,'admin','Owner','admin',?,?,1,0,?,'qa',1)",
            (salt, ph, ns.now_iso()),
        )
        conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('owner_setup_complete','1')")
        conn.commit()
    errors = []
    with ns.app.app_context():
        c = ns.app.test_client()
        c.post("/login", data={"username": "admin", "password": "TestPass123!"})
        for path in ("/", "/setup-complete"):
            r = c.get(path, follow_redirects=True)
            html = (r.data or b"").decode("utf-8", errors="ignore")
            if r.status_code >= 400:
                errors.append(f"{path} status {r.status_code}")
            for needle in ("Owner Command Center", "action-grid", "Admin Hub", "Jobs"):
                if needle not in html:
                    errors.append(f"{path} missing {needle}")
            if html.count("action-grid") < 2:
                errors.append(f"{path} expected multiple action-grid sections, got {html.count('action-grid')}")
    if errors:
        print("DASHBOARD LIVE CHECK: FAIL")
        for e in errors:
            print(" -", e)
        return 1
    print("DASHBOARD LIVE CHECK: PASS — admin dashboard tiles visible on / and /setup-complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
