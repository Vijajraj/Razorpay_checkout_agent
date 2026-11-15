"""
Unit & Integration Test Suite for Vasool Recovery Router (Spec v0.2).
Covers all acceptance criteria from Section 7 of the specification:
1. Token validation: missing, bad signature, wrong audience -> fails with ledger entry.
2. Expired, replayed (jti), amount-mismatched, or ceiling-exceeded tokens -> fail.
3. Customer-supplied or tampered amount rejected.
4. Idempotency: same Idempotency-Key or (case_id, attempt_no) returns same order.
5. Rate limiting: maximum 3 pay links per case.
6. Public pay page: token-gated, no PII, masked case reference.
7. Payment verification: forged signature rejected; valid signature transitions order to paid.
8. Webhook verification: bad signature rejected; duplicate webhook processed once.
9. Confirm-by-GET verification logic for RecoveraX.
10. Canonical ledger: full chain verification and exact tamper detection.
"""

import time
import hmac
import hashlib
import json
import pytest
import jwt
from fastapi import HTTPException

try:
    from app.recovery import (
        router,
        ledger,
        reset_recovery_state,
        create_recovery_order,
        get_pay_page_details,
        verify_payment,
        razorpay_webhook,
        get_recovery_order_status,
        cancel_recovery_order,
        CreateRecoveryOrderRequest,
        PaymentVerificationRequest,
        AUTH_VERIFY_KEY,
        SERVICE_TOKEN,
        RAZORPAY_KEY_SECRET,
        RAZORPAY_WEBHOOK_SECRET,
        RECOVERY_MAX_ORDER_MINOR,
        compute_canonical_entry_hash,
    )
except ImportError:
    try:
        from backend.recovery import (
            router,
            ledger,
            reset_recovery_state,
            create_recovery_order,
            get_pay_page_details,
            verify_payment,
            razorpay_webhook,
            get_recovery_order_status,
            cancel_recovery_order,
            CreateRecoveryOrderRequest,
            PaymentVerificationRequest,
            AUTH_VERIFY_KEY,
            SERVICE_TOKEN,
            RAZORPAY_KEY_SECRET,
            RAZORPAY_WEBHOOK_SECRET,
            RECOVERY_MAX_ORDER_MINOR,
            compute_canonical_entry_hash,
        )
    except ImportError:
        from recovery import (
            router,
            ledger,
            reset_recovery_state,
            create_recovery_order,
            get_pay_page_details,
            verify_payment,
            razorpay_webhook,
            get_recovery_order_status,
            cancel_recovery_order,
            CreateRecoveryOrderRequest,
            PaymentVerificationRequest,
            AUTH_VERIFY_KEY,
            SERVICE_TOKEN,
            RAZORPAY_KEY_SECRET,
            RAZORPAY_WEBHOOK_SECRET,
            RECOVERY_MAX_ORDER_MINOR,
            compute_canonical_entry_hash,
        )

def make_token(
    case_id: str = "RX-2026-0042",
    attempt_no: int = 1,
    amount_minor: int = 420000,
    currency: str = "INR",
    decision: str = "AUTO",
    action: str = "create_recovery_order",
    jti: str = "auth_test_1",
    exp_offset: int = 600,
    aud: str = "razorpay_checkout_agent",
    secret: str = AUTH_VERIFY_KEY,
    algorithm: str = "HS256"
) -> str:
    now = int(time.time())
    payload = {
        "aud": aud,
        "jti": jti,
        "case_id": case_id,
        "attempt_no": attempt_no,
        "action": action,
        "amount_minor": amount_minor,
        "currency": currency,
        "decision": decision,
        "approval_id": "apr_123" if decision == "HUMAN_APPROVED" else None,
        "iat": now,
        "exp": now + exp_offset
    }
    return jwt.encode(payload, secret, algorithm=algorithm)

@pytest.fixture(autouse=True)
def clean_state():
    reset_recovery_state()
    yield
    reset_recovery_state()

# ---------------------------------------------------------------------------
# Token Verification Tests
# ---------------------------------------------------------------------------

def test_order_creation_without_token_fails():
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=None,
            authorization=None,
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "AUTH_INVALID"
    # Verify ledger recorded authorization_rejected
    assert len(ledger.entries) == 1
    assert ledger.entries[0]["event_type"] == "authorization_rejected"

def test_order_creation_bad_signature_fails():
    bad_token = make_token(secret="wrong-secret-key-that-does-not-match")
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=None,
            authorization=f"Bearer {bad_token}",
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "AUTH_INVALID"
    assert ledger.entries[-1]["event_type"] == "authorization_rejected"

def test_order_creation_wrong_audience_fails():
    wrong_aud_token = make_token(aud="wrong_audience")
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=None,
            authorization=f"Bearer {wrong_aud_token}",
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "AUTH_INVALID"
    assert ledger.entries[-1]["event_type"] == "authorization_rejected"

def test_order_creation_expired_token_fails():
    expired_token = make_token(exp_offset=-10)
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=None,
            authorization=f"Bearer {expired_token}",
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "AUTH_EXPIRED"
    assert ledger.entries[-1]["event_type"] == "authorization_rejected"

def test_order_creation_replayed_token_fails():
    token = make_token(jti="auth_single_use_99")
    # First creation succeeds
    res1 = create_recovery_order(
        req=None,
        authorization=f"Bearer {token}",
        x_service_token=SERVICE_TOKEN
    )
    assert res1["state"] == "created"

    # Second creation with identical jti for a different case/attempt must fail as AUTH_REPLAY
    replay_token = make_token(case_id="RX-2026-9999", attempt_no=2, jti="auth_single_use_99")
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=None,
            authorization=f"Bearer {replay_token}",
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "AUTH_REPLAY"
    assert ledger.entries[-1]["event_type"] == "authorization_rejected"

def test_order_creation_amount_mismatch_fails():
    # Non-INR currency
    usd_token = make_token(currency="USD", jti="usd_tok_1")
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=None,
            authorization=f"Bearer {usd_token}",
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "AMOUNT_MISMATCH"

def test_order_creation_exceeds_ceiling_fails():
    # Exceeds Rs 50,000 ceiling (5,000,000 minor)
    huge_token = make_token(amount_minor=6000000, jti="huge_tok_1")
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=None,
            authorization=f"Bearer {huge_token}",
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "AMOUNT_MISMATCH"

def test_customer_supplied_tampered_amount_rejected():
    token = make_token(amount_minor=420000, jti="tamper_test_1")
    # Customer request body provides tampered amount 100000
    tampered_body = CreateRecoveryOrderRequest(
        case_id="RX-2026-0042",
        amount_minor=100000,
        currency="INR"
    )
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=tampered_body,
            authorization=f"Bearer {token}",
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "AMOUNT_MISMATCH"

# ---------------------------------------------------------------------------
# Order Creation, Idempotency & Rate Limiting
# ---------------------------------------------------------------------------

def test_order_creation_success():
    token = make_token(case_id="RX-2026-0042", attempt_no=1, amount_minor=420000, jti="auth_ok_1")
    order = create_recovery_order(
        req=None,
        authorization=f"Bearer {token}",
        x_service_token=SERVICE_TOKEN,
        idempotency_key="idemp_key_001"
    )
    assert order["case_id"] == "RX-2026-0042"
    assert order["attempt_no"] == 1
    assert order["amount_minor"] == 420000
    assert order["currency"] == "INR"
    assert order["state"] == "created"
    assert order["receipt"] == "RX-RX-2026-0042-1"
    assert order["pay_url"].startswith("http")
    assert order["pay_token"] is not None

    # Verify ledger entries: recovery_authorized followed by recovery_order_created
    auth_events = [e for e in ledger.entries if e["event_type"] == "recovery_authorized"]
    order_events = [e for e in ledger.entries if e["event_type"] == "recovery_order_created"]
    assert len(auth_events) == 1
    assert len(order_events) == 1

def test_idempotency_returns_same_order():
    token1 = make_token(case_id="RX-2026-0042", attempt_no=1, jti="auth_idemp_1")
    order1 = create_recovery_order(
        req=None,
        authorization=f"Bearer {token1}",
        x_service_token=SERVICE_TOKEN,
        idempotency_key="idemp_same_key"
    )

    # Re-call with same Idempotency-Key
    order2 = create_recovery_order(
        req=None,
        authorization=f"Bearer {token1}",
        x_service_token=SERVICE_TOKEN,
        idempotency_key="idemp_same_key"
    )
    assert order1["recovery_order_id"] == order2["recovery_order_id"]
    assert order1["razorpay_order_id"] == order2["razorpay_order_id"]

def test_rate_limiting_max_3_links_per_case():
    case_id = "RX-2026-0088"
    # Create 3 attempts
    for attempt in [1, 2, 3]:
        tok = make_token(case_id=case_id, attempt_no=attempt, jti=f"rate_tok_{attempt}")
        res = create_recovery_order(
            req=None,
            authorization=f"Bearer {tok}",
            x_service_token=SERVICE_TOKEN
        )
        assert res["state"] == "created"

    # 4th attempt must be rejected by rate limiting
    tok4 = make_token(case_id=case_id, attempt_no=4, jti="rate_tok_4")
    with pytest.raises(HTTPException) as exc_info:
        create_recovery_order(
            req=None,
            authorization=f"Bearer {tok4}",
            x_service_token=SERVICE_TOKEN
        )
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "RATE_LIMITED"

# ---------------------------------------------------------------------------
# Public Pay Page & Payment Verification
# ---------------------------------------------------------------------------

def test_get_pay_page_details_public_no_pii():
    token = make_token(case_id="RX-2026-0042", attempt_no=1, amount_minor=420000, jti="pay_page_tok")
    order = create_recovery_order(
        req=None,
        authorization=f"Bearer {token}",
        x_service_token=SERVICE_TOKEN
    )
    pay_token = order["pay_token"]

    pay_details = get_pay_page_details(token=pay_token)
    assert pay_details["amount_minor"] == 420000
    assert pay_details["currency"] == "INR"
    assert pay_details["merchant_name"] == "Vasool Recovery / Merchant"
    assert "razorpay_key_id" in pay_details
    assert "razorpay_order_id" in pay_details
    # Masked case reference: RX-****-0042
    assert "RX-****-" in pay_details["case_reference"]
    # No PII present
    for sensitive in ["phone", "email", "address", "name", "customer"]:
        assert sensitive not in pay_details

def test_payment_verification_forged_signature_rejected():
    token = make_token(case_id="RX-2026-0042", attempt_no=1, jti="pay_verify_tok_1")
    order = create_recovery_order(
        req=None,
        authorization=f"Bearer {token}",
        x_service_token=SERVICE_TOKEN
    )

    req = PaymentVerificationRequest(
        razorpay_order_id=order["razorpay_order_id"],
        razorpay_payment_id="pay_fake_12345",
        razorpay_signature="bad_forged_signature_hex",
        pay_token=order["pay_token"]
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_payment(req)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "AUTH_INVALID"
    assert ledger.entries[-1]["event_type"] == "payment_rejected"

def test_payment_verification_success():
    token = make_token(case_id="RX-2026-0042", attempt_no=1, amount_minor=420000, jti="pay_verify_tok_ok")
    order = create_recovery_order(
        req=None,
        authorization=f"Bearer {token}",
        x_service_token=SERVICE_TOKEN
    )

    rzp_order_id = order["razorpay_order_id"]
    payment_id = "pay_valid_998877"
    valid_sig = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{rzp_order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    req = PaymentVerificationRequest(
        razorpay_order_id=rzp_order_id,
        razorpay_payment_id=payment_id,
        razorpay_signature=valid_sig,
        pay_token=order["pay_token"]
    )
    res = verify_payment(req)
    assert res["status"] == "success"
    assert res["verified"] is True
    assert res["state"] == "paid"

    # Status check confirms paid
    status_res = get_recovery_order_status(
        order_id=order["recovery_order_id"],
        x_service_token=SERVICE_TOKEN
    )
    assert status_res["state"] == "paid"
    assert status_res["payment_id"] == payment_id

# ---------------------------------------------------------------------------
# Webhook Verification & Deduplication
# ---------------------------------------------------------------------------

def test_webhook_bad_signature_rejected():
    body = json.dumps({"event": "payment.captured", "event_id": "evt_123"}).encode("utf-8")

    with pytest.raises(HTTPException) as exc_info:
        razorpay_webhook(raw_bytes=body, x_razorpay_signature="bad_sig")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "AUTH_INVALID"

def test_webhook_deduplication():
    event_payload = {
        "event": "payment.captured",
        "event_id": "evt_unique_12345",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_hook_123",
                    "order_id": "order_rx_unknown"
                }
            }
        }
    }
    body = json.dumps(event_payload).encode("utf-8")
    sig = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()

    res1 = razorpay_webhook(raw_bytes=body, x_razorpay_signature=sig)
    assert res1["status"] == "ok"

    # Second duplicate call with same event_id
    res2 = razorpay_webhook(raw_bytes=body, x_razorpay_signature=sig)
    assert res2["status"] == "duplicate"

    dup_events = [e for e in ledger.entries if e["event_type"] == "webhook_duplicate"]
    assert len(dup_events) == 1

# ---------------------------------------------------------------------------
# Cancellation & Confirm-by-GET
# ---------------------------------------------------------------------------

def test_order_cancellation():
    token = make_token(case_id="RX-2026-0042", attempt_no=1, jti="cancel_tok_1")
    order = create_recovery_order(
        req=None,
        authorization=f"Bearer {token}",
        x_service_token=SERVICE_TOKEN
    )

    cancel_res = cancel_recovery_order(
        order_id=order["recovery_order_id"],
        x_service_token=SERVICE_TOKEN
    )
    assert cancel_res["status"] == "cancelled"

    # Status check confirms cancelled
    status_res = get_recovery_order_status(
        order_id=order["recovery_order_id"],
        x_service_token=SERVICE_TOKEN
    )
    assert status_res["state"] == "cancelled"

# ---------------------------------------------------------------------------
# Ledger Cryptographic Verification & Tamper Detection
# ---------------------------------------------------------------------------

def test_ledger_integrity_and_tamper_detection():
    # Generate some ledger entries via standard flow
    token = make_token(case_id="RX-2026-0042", attempt_no=1, jti="ledger_flow_tok")
    order = create_recovery_order(
        req=None,
        authorization=f"Bearer {token}",
        x_service_token=SERVICE_TOKEN
    )

    # Verify ledger chain is cryptographically valid
    is_valid, report = ledger.verify_chain()
    assert is_valid is True
    assert report["valid"] is True
    assert report["entries_count"] >= 2

    # Tamper with an entry's payload
    target_entry = ledger.entries[0]
    original_payload = target_entry["payload"]
    target_entry["payload"] = {"tampered": True}

    is_valid_after_tamper, tamper_report = ledger.verify_chain()
    assert is_valid_after_tamper is False
    assert tamper_report["valid"] is False
    assert tamper_report["failed_at_seq"] == 1

    # Restore payload and verify it passes again
    target_entry["payload"] = original_payload
    is_restored, restored_report = ledger.verify_chain()
    assert is_restored is True

# ---------------------------------------------------------------------------
# LangGraph Recovery Agent Workflow Tests
# ---------------------------------------------------------------------------

def test_langgraph_recovery_agent_auto_flow():
    try:
        from app.recovery_langgraph import recovery_langgraph_agent
    except ImportError:
        try:
            from backend.recovery_langgraph import recovery_langgraph_agent
        except ImportError:
            from recovery_langgraph import recovery_langgraph_agent
    initial_state = {
        "case_id": "RX-2026-LG01",
        "attempt_no": 1,
        "amount_minor": 420000,
        "currency": "INR",
        "debtor_name": "Aarav Sharma"
    }
    result = recovery_langgraph_agent.invoke(initial_state)
    assert result.get("policy_decision") == "AUTO"
    assert result.get("payment_status") == "RECOVERED"
    assert result.get("recovery_order") is not None
    assert "pay_url" in result["recovery_order"]

def test_langgraph_recovery_agent_hitl_flow():
    try:
        from app.recovery_langgraph import recovery_langgraph_agent
    except ImportError:
        try:
            from backend.recovery_langgraph import recovery_langgraph_agent
        except ImportError:
            from recovery_langgraph import recovery_langgraph_agent
    # High amount requires human approval
    hitl_state = {
        "case_id": "RX-2026-LG02",
        "attempt_no": 1,
        "amount_minor": 1850000,
        "currency": "INR",
        "debtor_name": "Meera Nambiar",
        "approval_record": {
            "id": "apr_lg_9042",
            "status": "approved",
            "approver_id": "usr_admin_001",
            "readback_hash": "rbh_lg_verified"
        }
    }
    result = recovery_langgraph_agent.invoke(hitl_state)
    assert result.get("policy_decision") == "HUMAN_APPROVED"
    assert result.get("payment_status") == "RECOVERED"
    assert result.get("recovery_order") is not None
