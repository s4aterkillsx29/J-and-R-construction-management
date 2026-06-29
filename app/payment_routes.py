"""Flask routes for debit payments, holds, and admin withdrawals."""
from __future__ import annotations

import html
from typing import Any, Callable

from flask import abort, flash, redirect, request, session, url_for

from app.payment_system import (
    DEBIT_CARD_FEE_RATE,
    admin_withdraw,
    calc_debit_total,
    confirm_payment,
    create_payment_request,
    ensure_payment_schema,
    funds_balance,
    get_pending_request_for_user,
    list_recent_requests,
    mark_paid_awaiting_confirmation,
    money,
    user_has_payment_lock,
)


def register_payment_routes(app, db, layout, login_required, now_iso) -> None:
    @app.before_request
    def _payment_schema():
        try:
            ensure_payment_schema(db())
        except Exception:
            pass

    @app.before_request
    def _enforce_payment_lock():
        exempt = (
            None, "static", "login", "logout", "public_account_request",
            "user_payment_required", "user_submit_payment", "payments_complete",
            "payments_cancel", "stripe_webhook", "emergency_access",
        )
        if request.endpoint in exempt:
            return
        uid = session.get("user_id")
        if not uid:
            return
        lock = user_has_payment_lock(db(), uid)
        if lock and request.endpoint not in ("user_payment_required", "user_submit_payment", "change_password"):
            return redirect(url_for("user_payment_required"))

    @app.route("/payments/required")
    @login_required()
    def user_payment_required():
        uid = session["user_id"]
        req = get_pending_request_for_user(db(), uid)
        lock = user_has_payment_lock(db(), uid)
        if not req and not lock:
            return redirect(url_for("dashboard"))
        body = f"""
        <div class='card'><h2>Payment Required</h2>
        <p class='muted'>Your account is locked until the requested payment is received and confirmed by an administrator.</p>
        <p><b>Reason:</b> {html.escape(lock['lock_reason'] if lock else '')}</p>
        """
        if req:
            body += f"""
        <p><b>Amount:</b> ${money(req['amount']):,.2f}<br>
        <b>Debit card fee ({int(DEBIT_CARD_FEE_RATE*100)}%):</b> ${money(req['fee_amount']):,.2f}<br>
        <b>Total due:</b> ${money(req['total_due']):,.2f}</p>
        <p><b>Reference code:</b> {html.escape(req['request_code'])}</p>
        """
            if req["stripe_checkout_url"]:
                body += f"<p><a class='btn' href='{html.escape(req['stripe_checkout_url'])}' target='_blank'>Pay Securely with Debit Card</a></p>"
            body += f"""
        <form method='post' action='/payments/submit'>
          <input type='hidden' name='request_id' value='{req['id']}'>
          <p><label>Payment reference (last 4 / confirmation #)</label><input name='payer_reference' required placeholder='Debit confirmation'></p>
          <button>I Have Paid — Request Admin Confirmation</button>
        </form>
        """
        body += "<p><a class='btn btn2' href='/logout'>Sign out</a></p></div>"
        return layout("Payment Required", body, "dashboard")

    @app.route("/payments/submit", methods=["POST"])
    @login_required()
    def user_submit_payment():
        rid = int(request.form.get("request_id", "0") or 0)
        ref = request.form.get("payer_reference", "").strip()
        mark_paid_awaiting_confirmation(db(), rid, ref)
        flash("Payment submitted for admin confirmation. Access unlocks after confirmation.", "success")
        return redirect(url_for("user_payment_required"))

    @app.route("/payments/complete")
    def payments_complete():
        code = request.args.get("code", "").strip()
        session_id = request.args.get("session_id", "").strip()
        if code and session_id:
            from app.stripe_integration import handle_checkout_completed, retrieve_checkout_session
            sess = retrieve_checkout_session(session_id)
            if sess and sess.get("payment_status") == "paid":
                ok, msg = handle_checkout_completed(db(), code, "stripe_checkout")
                flash(msg if ok else "Payment received — awaiting confirmation.", "success" if ok else "warning")
                return redirect(url_for("login"))
        flash("If Stripe payment succeeded, your account unlocks after confirmation.", "success")
        return redirect(url_for("login"))

    @app.route("/payments/cancel")
    def payments_cancel():
        flash("Payment cancelled. You can try again from the payment required screen.", "warning")
        return redirect(url_for("login"))

    @app.route("/payments/stripe/webhook", methods=["POST"])
    def stripe_webhook():
        from app.stripe_integration import handle_checkout_completed, verify_webhook_signature
        payload = request.get_data()
        sig = request.headers.get("Stripe-Signature", "")
        if not verify_webhook_signature(payload, sig):
            return {"error": "invalid signature"}, 400
        try:
            import json as _json
            event = _json.loads(payload.decode("utf-8"))
        except Exception:
            return {"error": "bad payload"}, 400
        if event.get("type") == "checkout.session.completed":
            obj = event.get("data", {}).get("object", {})
            code = (obj.get("metadata") or {}).get("request_code", "")
            if code and obj.get("payment_status") == "paid":
                handle_checkout_completed(db(), code, "stripe_webhook")
        return {"ok": True}

    @app.route("/admin/payments", methods=["GET", "POST"])
    @login_required("view_admin")
    def admin_payments():
        if request.method == "POST":
            action = request.form.get("action", "")
            if action == "request":
                uid = int(request.form.get("user_id", "0") or 0)
                user = db().execute("SELECT id, username FROM users WHERE id=?", (uid,)).fetchone()
                if user:
                    amt = float(request.form.get("amount", "0") or 0)
                    reason = request.form.get("reason", "Administrative payment request")
                    create_payment_request(db(), user["id"], user["username"], amt, reason, session.get("username", "admin"), True)
                    flash(f"Payment request created and {user['username']} locked until paid.", "success")
            elif action == "confirm":
                confirm_payment(db(), int(request.form.get("request_id", "0")), session.get("username", "admin"))
                flash("Payment confirmed and user unlocked.", "success")
            elif action == "withdraw":
                ok, msg = admin_withdraw(
                    db(),
                    float(request.form.get("amount", "0") or 0),
                    request.form.get("method", "Bank transfer"),
                    request.form.get("destination", ""),
                    session.get("username", "admin"),
                    request.form.get("notes", ""),
                )
                flash(msg, "success" if ok else "error")
            return redirect(url_for("admin_payments"))
        bal = funds_balance(db())
        users = db().execute("SELECT id, username, role, access_locked FROM users WHERE active=1 ORDER BY username").fetchall()
        reqs = list_recent_requests(db())
        user_opts = "".join(f"<option value='{u['id']}'>{html.escape(u['username'])} ({u['role']})</option>" for u in users)
        req_rows = "".join(
            f"<tr><td>{html.escape(r['request_code'])}</td><td>{html.escape(r['username'])}</td>"
            f"<td>${money(r['amount']):,.2f}</td><td>${money(r['fee_amount']):,.2f}</td><td>${money(r['total_due']):,.2f}</td>"
            f"<td>{html.escape(r['status'])}</td><td>"
            + (f"<form method='post' style='display:inline'><input type='hidden' name='action' value='confirm'><input type='hidden' name='request_id' value='{r['id']}'><button>Confirm</button></form>" if r["status"] == "Awaiting Confirmation" else "")
            + "</td></tr>"
            for r in reqs
        )
        body = f"""
        <div class='card'><h2>Business Funds (Held Balance)</h2>
        <p><b>Available to withdraw:</b> ${bal:,.2f}</p>
        <p class='muted'>Debit card payments include a {int(DEBIT_CARD_FEE_RATE*100)}% processing fee. Funds are held in the ledger until you withdraw.</p></div>
        <div class='card'><h2>Request Payment from User</h2>
        <form method='post'><input type='hidden' name='action' value='request'>
        <div class='row3'><p><label>User</label><select name='user_id'>{user_opts}</select></p>
        <p><label>Amount ($)</label><input name='amount' required placeholder='100.00'></p>
        <p><label>Reason</label><input name='reason' placeholder='Subscription, deposit, overdue invoice'></p></div>
        <button>Request Payment &amp; Lock User</button></form></div>
        <div class='card'><h2>Withdraw Funds</h2>
        <form method='post'><input type='hidden' name='action' value='withdraw'>
        <div class='row3'><p><label>Amount</label><input name='amount' required></p>
        <p><label>Method</label><select name='method'><option>Bank transfer</option><option>Debit to owner card</option><option>Cash</option><option>Check</option></select></p>
        <p><label>Destination</label><input name='destination' placeholder='Account / card last 4'></p></div>
        <p><label>Notes</label><textarea name='notes'></textarea></p>
        <button>Withdraw Now</button></form></div>
        <div class='card'><h2>Payment Requests</h2>
        <table><tr><th>Code</th><th>User</th><th>Base</th><th>Fee</th><th>Total</th><th>Status</th><th>Action</th></tr>{req_rows}</table></div>
        """
        return layout("Payments & Holds", body, "admin")
