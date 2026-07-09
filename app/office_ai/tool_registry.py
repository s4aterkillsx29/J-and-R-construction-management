# -*- coding: utf-8 -*-
"""Register Office AI tools and OpenAI function schemas."""
from __future__ import annotations

from typing import Any, Dict, List

from app.office_ai import approval_gate
from app.office_ai.tools import (
    admin_audit_active_sessions,
    admin_propose_access_change,
    admin_recommend_account_role,
    admin_review_user_permissions,
    admin_run_security_audit,
    admin_summarize_pending_accounts,
    generate_customer_pdf,
    generate_office_brief,
    list_program_modules,
    office_mgmt_check_tax_savings_plan,
    office_mgmt_draft_log_entry,
    office_mgmt_follow_up_leads,
    office_mgmt_triage_inbox_photos,
    office_mgmt_triage_todo_list,
    office_mgmt_update_dashboard_note,
    quote_build_quote_package,
    quote_calculate_job_costing,
    quote_compare_quote_to_sent,
    quote_draft_quote_scope,
    quote_read_internal_workup,
    quote_read_similar_jobs,
    read_dashboard,
    read_financial_register,
    read_job_folder,
    read_job_register,
    read_logging_checklist,
    read_program_source,
    read_program_structure,
    read_security_policies,
    read_standards_file,
    run_consistency_audit,
    run_workspace_sync,
    save_receipt_note,
    search_business_records,
    search_chatgpt_imports,
    update_csv,
    verify_business_sources,
    write_daily_log,
)

_TOOL_MODULES = {
    "read_dashboard": read_dashboard,
    "read_job_register": read_job_register,
    "read_job_folder": read_job_folder,
    "search_chatgpt_imports": search_chatgpt_imports,
    "search_business_records": search_business_records,
    "read_logging_checklist": read_logging_checklist,
    "read_standards_file": read_standards_file,
    "read_financial_register": read_financial_register,
    "read_security_policies": read_security_policies,
    "verify_business_sources": verify_business_sources,
    "list_program_modules": list_program_modules,
    "read_program_structure": read_program_structure,
    "read_program_source": read_program_source,
    "append_daily_log": write_daily_log,
    "save_receipt_note": save_receipt_note,
    "update_financial_csv": update_csv,
    "run_workspace_sync": run_workspace_sync,
    "generate_customer_pdf": generate_customer_pdf,
    "generate_office_brief": generate_office_brief,
    "run_consistency_audit": run_consistency_audit,
    # Admin tools (Workstream E)
    "summarize_pending_accounts": admin_summarize_pending_accounts,
    "recommend_account_role": admin_recommend_account_role,
    "review_user_permissions": admin_review_user_permissions,
    "audit_active_sessions": admin_audit_active_sessions,
    "propose_access_change": admin_propose_access_change,
    "run_security_audit": admin_run_security_audit,
    # Office management tools (Workstream F)
    "triage_todo_list": office_mgmt_triage_todo_list,
    "check_tax_savings_plan": office_mgmt_check_tax_savings_plan,
    "draft_log_entry": office_mgmt_draft_log_entry,
    "follow_up_leads": office_mgmt_follow_up_leads,
    "triage_inbox_photos": office_mgmt_triage_inbox_photos,
    "update_dashboard_note": office_mgmt_update_dashboard_note,
    # Quote tools (Workstream G)
    "read_internal_workup": quote_read_internal_workup,
    "read_similar_jobs": quote_read_similar_jobs,
    "draft_quote_scope": quote_draft_quote_scope,
    "calculate_job_costing": quote_calculate_job_costing,
    "build_quote_package": quote_build_quote_package,
    "compare_quote_to_sent": quote_compare_quote_to_sent,
}


def tool_schemas() -> List[dict]:
    return [mod.SCHEMA for mod in _TOOL_MODULES.values()]


def run_tool(
    name: str,
    args: Dict[str, Any],
    *,
    conn,
    session_id: int,
    user_id: int,
    username: str,
) -> dict:
    mod = _TOOL_MODULES.get(name)
    if not mod:
        return {"ok": False, "error": f"Unknown tool: {name}"}

    try:
        if approval_gate.requires_approval(name):
            preview_fn = getattr(mod, "preview", None)
            if preview_fn:
                preview = preview_fn(**args)
            else:
                preview = mod.run(**args)
            if not preview.get("ok"):
                return preview
            preview_text = preview.get("preview_text") or str(preview)
            action_id = approval_gate.queue_action(
                conn,
                session_id=session_id,
                user_id=user_id,
                username=username,
                tool_name=name,
                args=args,
                preview_text=preview_text[:8000],
            )
            return {
                "ok": True,
                "pending_approval": True,
                "pending_approval_id": action_id,
                "preview": preview_text[:2000],
                "message": f"Queued for owner approval (#{action_id}). Review at /office-ai/approvals",
            }

        return mod.run(**args)
    except Exception as exc:
        return {"ok": False, "error": f"Tool {name} error: {exc}"}
