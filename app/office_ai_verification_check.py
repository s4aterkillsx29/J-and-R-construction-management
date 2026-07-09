# -*- coding: utf-8 -*-
"""Verify Office AI Phase 1 foundation."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
APP = BASE / "app"
PKG = APP / "office_ai"
errors: list[str] = []
notes: list[str] = []


def check(name: str, ok: bool, fail: str = "") -> None:
    if ok:
        notes.append(f"OK: {name}")
    else:
        errors.append(fail or name)


def main() -> int:
    required = [
        PKG / "orchestrator.py",
        PKG / "context_loader.py",
        PKG / "provider_router.py",
        PKG / "provider_fallback.py",
        PKG / "learning_store.py",
        PKG / "access.py",
        PKG / "tool_registry.py",
        PKG / "approval_gate.py",
        PKG / "routes.py",
        PKG / "config.py",
        PKG / "schema.py",
        PKG / "office_ai_sources.json",
        PKG / "providers" / "openai_provider.py",
        PKG / "providers" / "groq_provider.py",
        PKG / "providers" / "gemini_provider.py",
        PKG / "providers" / "anthropic_provider.py",
        PKG / "providers" / "ollama_provider.py",
        PKG / "providers" / "mock_provider.py",
        PKG / "tools" / "read_dashboard.py",
        PKG / "tools" / "write_daily_log.py",
        PKG / "path_security.py",
        PKG / "tools" / "verify_business_sources.py",
        PKG / "tools" / "search_business_records.py",
        PKG / "tools" / "read_program_source.py",
        PKG / "tools" / "run_workspace_sync.py",
        PKG / "tools" / "generate_customer_pdf.py",
    ]
    for p in required:
        check(f"file {p.name}", p.is_file())

    ns = (APP / "network_server.py").read_text(encoding="utf-8", errors="ignore")
    dc = (APP / "dashboard_config.py").read_text(encoding="utf-8", errors="ignore")
    check("register_office_ai_routes wired", "register_office_ai_routes" in ns)
    check("office_ai tables in init_db", "office_ai_sessions" in ns and "office_ai_pending_actions" in ns)
    check("Owner Command Center Office AI link", '("/office-ai"' in ns or '"/office-ai"' in ns)
    check("dashboard Office AI tile", "/office-ai" in dc and "configure_ai" in dc)
    check("admin-only access module", (PKG / "access.py").is_file())
    check("provider fallback", "complete_with_fallback" in (PKG / "provider_fallback.py").read_text(encoding="utf-8", errors="ignore"))
    check("learning store", "office_ai_learning_examples" in (PKG / "learning_store.py").read_text(encoding="utf-8", errors="ignore"))
    check("Start Center Office AI button", "open_office_ai" in (APP / "start_center.py").read_text(encoding="utf-8", errors="ignore"))
    check("Open Office session resume", "resume_user_from_desktop_session" in (APP / "office_app_session.py").read_text(encoding="utf-8", errors="ignore"))
    check("document standards writer", (APP / "document_standards_writer.py").is_file())

    routes_src = (PKG / "routes.py").read_text(encoding="utf-8", errors="ignore")
    check("/office-ai route", '"/office-ai"' in routes_src)
    check("/office-ai/approvals route", '"/office-ai/approvals"' in routes_src)
    check("/ai settings upgraded", "office_ai_default_provider" in routes_src)
    check("api chat route", "/api/office-ai/chat" in routes_src)

    ico = BASE / "assets" / "jrc_manager_app.ico"
    check("crisp manager icon (>=8KB multi-res ICO)", ico.is_file() and ico.stat().st_size >= 8000, f"icon size {ico.stat().st_size if ico.is_file() else 0}")

    check("legacy ai route removed from network_server", '@app.route("/ai"' not in ns)

    from app.office_ai.schema import ensure_office_ai_schema
    from app.office_ai.access import is_office_ai_user, office_ai_access_message
    check("admin user allowed", is_office_ai_user({"role": "admin", "active": 1}))
    check("manager blocked", not is_office_ai_user({"role": "manager", "active": 1}))
    from app.office_ai.config import encrypt_secret, decrypt_secret, set_setting
    from app.office_ai.context_loader import load_context
    from app.office_ai.tool_registry import tool_schemas, run_tool
    from app.office_ai.approval_gate import requires_approval
    from app.office_ai.orchestrator import OfficeAIOrchestrator

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);
            INSERT INTO users VALUES (1, 'admin');
            """
        )
        ensure_office_ai_schema(conn)
        enc = encrypt_secret(conn, "sk-test-key-12345")
        check("encrypt api key", enc.startswith("enc1:"))
        check("decrypt api key", decrypt_secret(conn, enc) == "sk-test-key-12345")
        set_setting(conn, "office_ai_enabled", "1")
        set_setting(conn, "office_ai_default_provider", "mock")

        ctx = load_context(tiers=["core"])
        check("context loader returns text", isinstance(ctx, str) and len(ctx) > 0)
        check("tool schemas", len(tool_schemas()) >= 18)
        tr_src = (PKG / "tool_registry.py").read_text(encoding="utf-8", errors="ignore")
        for tool in (
            "verify_business_sources",
            "read_security_policies",
            "search_business_records",
            "read_program_source",
            "list_program_modules",
            "run_workspace_sync",
            "generate_customer_pdf",
        ):
            check(f"tool registered {tool}", f'"{tool}"' in tr_src)
        check("csv update requires approval", requires_approval("update_financial_csv"))
        check("workspace sync requires approval", requires_approval("run_workspace_sync"))
        check("pdf generate requires approval", requires_approval("generate_customer_pdf"))
        check("daily log auto", not requires_approval("append_daily_log"))

        orch = OfficeAIOrchestrator(conn)
        result = orch.chat(user_id=1, username="admin", message="What is on the dashboard?")
        check("mock chat ok", result.get("ok") is True, str(result))
        check("session created", bool(result.get("session_id")))
        empty = orch.chat(user_id=1, username="admin", message="   ")
        check("empty message rejected", empty.get("ok") is False)

        conn.close()

    print("JRC Office AI Verification Check")
    print("Errors:", len(errors))
    for e in errors:
        print(" ERROR -", e)
    for n in notes:
        print(" ", n)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
