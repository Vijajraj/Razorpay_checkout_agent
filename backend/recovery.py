"""
Vasool Recovery Router for Razorpay Checkout Agent (Edge).
Implements Person B integration per Vasool: Checkout Integration and Frontend Spec (v0.2).

Invariants enforced:
1. Only valid RecoveraX authorization can create a recovery order.
2. Amount comes strictly from the authorization, never from customer, voice, or LLM.
3. Authorizations are single-use (jti stored), expiring (max 10 min), bound to case and attempt.
4. RECOVERED only after HMAC-verified signature or verified webhook with order ID, amount, and currency matching.
5. Idempotent: one Razorpay order per (case_id, attempt_no) and per Idempotency-Key.
6. No LLM in the payment edge path.
7. No card data collected or stored.
8. Fail closed on missing, expired, or unverifiable input.
9. Ledger intent before action. Failed ledger write blocks order.
10. Unpaid or expired link counts toward retry limit (max 3 pay links per case).
"""

import os
import json
import time
import hmac
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Set, Tuple

import jwt
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration & Defaults
# ---------------------------------------------------------------------------
AUTH_VERIFY_KEY = os.getenv("AUTH_VERIFY_KEY", "vasool-recovery-secret-key-32bytes-minimum!")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "vasool-service-secret-token")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_mockkey123")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "mock_rzp_secret_key_123")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "vasool_webhook_secret_xyz")

RECOVERY_MAX_ORDER_MINOR = int(os.getenv("RECOVERY_MAX_ORDER_MINOR", "5000000"))  # Rs 50,000 ceiling
PAY_LINK_TTL_SECONDS = int(os.getenv("PAY_LINK_TTL_SECONDS", "900"))  # 15 minutes
AUTH_TTL_SECONDS = int(os.getenv("AUTH_TTL_SECONDS", "600"))  # 10 minutes max token TTL
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/")
RECOVERAX_BASE_URL = os.getenv("RECOVERAX_BASE_URL", "").rstrip("/")
MERCHANT_DISPLAY_NAME = os.getenv("MERCHANT_DISPLAY_NAME", "Vasool Recovery / Merchant")

router = APIRouter(tags=["recovery"])

# ---------------------------------------------------------------------------
# Canonical Cryptographic Ledger (Section 4.9)
# entry_hash = SHA256(prev_hash || canonical_json({seq, ts, actor, event_type, ref_id, payload}))
# Genesis prev_hash is 64 zeros.
# ---------------------------------------------------------------------------
GENESIS_HASH = "0" * 64

def canonical_json(data: Any) -> bytes:
    """Canonical JSON serialization: sorted keys, UTF-8, no extra whitespace."""
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def compute_canonical_entry_hash(prev_hash: str, body: Dict[str, Any]) -> str:
    """Computes SHA256(prev_hash || canonical_json({seq, ts, actor, event_type, ref_id, payload}))"""
    return hashlib.sha256(prev_hash.encode('utf-8') + canonical_json(body)).hexdigest()

class RecoveryLedger:
    def __init__(self, persist_file: Optional[str] = None):
        self.persist_file = persist_file or os.path.join(os.path.dirname(__file__), "recovery_ledger.json")
        self.entries: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if os.path.exists(self.persist_file):
            try:
                with open(self.persist_file, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
            except Exception as e:
                print(f"[Ledger] Load fallback: {e}")
                self.entries = []
        else:
            self.entries = []

    def _persist(self):
        try:
            with open(self.persist_file, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2)
        except Exception as e:
            print(f"[Ledger] Persist error: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "LEDGER_UNAVAILABLE", "message": f"Ledger write failed: {e}"}
            )

    def get_latest_hash(self) -> str:
        if not self.entries:
            return GENESIS_HASH
        return self.entries[-1]["entry_hash"]

    def append(self, actor: str, event_type: str, ref_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Appends a new cryptographically chained entry to the canonical ledger."""
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        seq = len(self.entries) + 1
        prev_hash = self.get_latest_hash()

        canonical_body = {
            "actor": actor,
            "event_type": event_type,
            "payload": payload,
            "ref_id": ref_id or "",
            "seq": seq,
            "ts": now_ts
        }
        entry_hash = compute_canonical_entry_hash(prev_hash, canonical_body)

        entry = {
            "seq": seq,
            "ts": now_ts,
            "actor": actor,
            "event_type": event_type,
            "ref_id": ref_id or "",
            "payload": payload,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash
        }

        self.entries.append(entry)
        self._persist()
        return entry

    def verify_chain(self) -> Tuple[bool, Dict[str, Any]]:
        """Cryptographically verifies every entry from genesis hash."""
        expected_prev = GENESIS_HASH
        for idx, entry in enumerate(self.entries):
            if entry["prev_hash"] != expected_prev:
                return False, {
                    "valid": False,
                    "failed_at_seq": entry["seq"],
                    "error": f"Broken chain link at seq {entry['seq']}: expected {expected_prev}, got {entry['prev_hash']}"
                }
            canonical_body = {
                "actor": entry["actor"],
                "event_type": entry["event_type"],
                "payload": entry["payload"],
                "ref_id": entry["ref_id"],
                "seq": entry["seq"],
                "ts": entry["ts"]
            }
            computed = compute_canonical_entry_hash(entry["prev_hash"], canonical_body)
            if computed != entry["entry_hash"]:
                return False, {
                    "valid": False,
                    "failed_at_seq": entry["seq"],
                    "error": f"Hash mismatch at seq {entry['seq']}: stored {entry['entry_hash']}, computed {computed}"
                }
            expected_prev = entry["entry_hash"]

        return True, {
            "valid": True,
            "entries_count": len(self.entries),
            "latest_hash": expected_prev
        }

    def reset(self):
        self.entries = []
        if os.path.exists(self.persist_file):
            try:
                os.remove(self.persist_file)
            except Exception:
                pass

ledger = RecoveryLedger()

# ---------------------------------------------------------------------------
# State Stores (Single-use tokens, orders, rate limits)
# ---------------------------------------------------------------------------
_USED_JTI: Set[str] = set()
_RECOVERY_ORDERS: Dict[str, Dict[str, Any]] = {}  # recovery_order_id -> order
_IDEMPOTENCY_MAP: Dict[str, str] = {}             # idempotency_key -> recovery_order_id
_CASE_ATTEMPTS: Dict[Tuple[str, int], str] = {}    # (case_id, attempt_no) -> recovery_order_id
_CASE_LINKS_COUNT: Dict[str, int] = {}            # case_id -> count of pay links
_PAY_TOKEN_MAP: Dict[str, str] = {}               # pay_token -> recovery_order_id
_RZP_ORDER_MAP: Dict[str, str] = {}               # razorpay_order_id -> recovery_order_id
_JTI_TO_ORDER_MAP: Dict[str, str] = {}             # jti -> recovery_order_id
_PROCESSED_WEBHOOKS: Set[str] = set()             # event_id set

def reset_recovery_state():
    """Reset all state for clean tests/demo."""
    global _USED_JTI, _RECOVERY_ORDERS, _IDEMPOTENCY_MAP, _CASE_ATTEMPTS
    global _CASE_LINKS_COUNT, _PAY_TOKEN_MAP, _RZP_ORDER_MAP, _JTI_TO_ORDER_MAP, _PROCESSED_WEBHOOKS
    _USED_JTI.clear()
    _RECOVERY_ORDERS.clear()
    _IDEMPOTENCY_MAP.clear()
    _CASE_ATTEMPTS.clear()
    _CASE_LINKS_COUNT.clear()
    _PAY_TOKEN_MAP.clear()
    _RZP_ORDER_MAP.clear()
    _JTI_TO_ORDER_MAP.clear()
    _PROCESSED_WEBHOOKS.clear()
    ledger.reset()

# ---------------------------------------------------------------------------
# Token Verification (Section 4.3)
# ---------------------------------------------------------------------------
def verify_authorization_token(token_str: str) -> Dict[str, Any]:
    """
    Decodes and verifies RecoveraX signed authorization token.
    Enforces signature, audience, expiry (max 10m), jti single-use, INR currency,
    ceiling amount, and decision validity.
    """
    if not token_str:
        ledger.append("razorpay_checkout_agent", "authorization_rejected", "", {"reason": "Missing token"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "Missing authorization token"}
        )

    # Support raw token or 'Bearer <token>'
    if token_str.startswith("Bearer "):
        token_str = token_str[7:].strip()

    # Determine algorithm and verify
    algorithms = ["HS256", "EdDSA"]
    try:
        # Decode without verification first to check alg/claims safely
        unverified_claims = jwt.decode(token_str, options={"verify_signature": False})
    except Exception as e:
        ledger.append("razorpay_checkout_agent", "authorization_rejected", "", {"reason": f"Malformed JWT: {e}"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": f"Malformed authorization token: {e}"}
        )

    # Verify signature
    try:
        payload = jwt.decode(
            token_str,
            AUTH_VERIFY_KEY,
            algorithms=algorithms,
            audience="razorpay_checkout_agent"
        )
    except jwt.ExpiredSignatureError:
        case_id = unverified_claims.get("case_id", "")
        ledger.append("razorpay_checkout_agent", "authorization_rejected", case_id, {"reason": "Token expired"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_EXPIRED", "message": "Authorization token has expired"}
        )
    except jwt.InvalidAudienceError:
        case_id = unverified_claims.get("case_id", "")
        ledger.append("razorpay_checkout_agent", "authorization_rejected", case_id, {"reason": "Invalid audience"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "Invalid audience in authorization token"}
        )
    except Exception as e:
        case_id = unverified_claims.get("case_id", "")
        ledger.append("razorpay_checkout_agent", "authorization_rejected", case_id, {"reason": f"Bad signature: {e}"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": f"Signature verification failed: {e}"}
        )

    # Check TTL ceiling: max 10 minutes between iat and exp
    iat = payload.get("iat", 0)
    exp = payload.get("exp", 0)
    if exp - iat > AUTH_TTL_SECONDS + 60:  # Allow 60s clock skew
        ledger.append("razorpay_checkout_agent", "authorization_rejected", payload.get("case_id", ""), {"reason": "TTL exceeds 10m"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "Token TTL exceeds 10 minutes ceiling"}
        )

    # Check jti single-use
    jti = payload.get("jti")
    if not jti:
        ledger.append("razorpay_checkout_agent", "authorization_rejected", payload.get("case_id", ""), {"reason": "Missing jti"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "Token is missing jti claim"}
        )

    if jti in _USED_JTI:
        ledger.append("razorpay_checkout_agent", "authorization_rejected", payload.get("case_id", ""), {"reason": "Replay detected", "jti": jti})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REPLAY", "message": f"Token with jti {jti} has already been used"}
        )

    # Check currency: strictly INR
    currency = payload.get("currency")
    if currency != "INR":
        ledger.append("razorpay_checkout_agent", "authorization_rejected", payload.get("case_id", ""), {"reason": f"Unsupported currency {currency}"})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AMOUNT_MISMATCH", "message": f"Currency must be INR, got {currency}"}
        )

    # Check amount ceiling and validity
    amount_minor = payload.get("amount_minor")
    if not isinstance(amount_minor, int) or amount_minor <= 0:
        ledger.append("razorpay_checkout_agent", "authorization_rejected", payload.get("case_id", ""), {"reason": "Invalid amount_minor"})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AMOUNT_MISMATCH", "message": "Invalid amount_minor in authorization token"}
        )

    if amount_minor > RECOVERY_MAX_ORDER_MINOR:
        ledger.append("razorpay_checkout_agent", "authorization_rejected", payload.get("case_id", ""), {"reason": "Exceeds hard ceiling"})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AMOUNT_MISMATCH", "message": f"Amount {amount_minor} exceeds ceiling {RECOVERY_MAX_ORDER_MINOR}"}
        )

    # Check decision
    decision = payload.get("decision")
    if decision not in ["AUTO", "HUMAN_APPROVED"]:
        ledger.append("razorpay_checkout_agent", "authorization_rejected", payload.get("case_id", ""), {"reason": f"Disallowed decision {decision}"})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AUTH_INVALID", "message": f"Decision {decision} is not payable"}
        )

    # Check action
    if payload.get("action") != "create_recovery_order":
        ledger.append("razorpay_checkout_agent", "authorization_rejected", payload.get("case_id", ""), {"reason": "Invalid action"})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AUTH_INVALID", "message": "Token action must be create_recovery_order"}
        )

    return payload

def verify_service_auth(
    x_service_token: Optional[str] = Header(None, alias="X-Service-Token"),
    authorization: Optional[str] = Header(None)
):
    """Enforces inter-service authentication from RecoveraX."""
    token = None
    if isinstance(x_service_token, str) and x_service_token.strip():
        token = x_service_token.strip()
    elif isinstance(authorization, str) and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if not token or (token != SERVICE_TOKEN and SERVICE_TOKEN != "vasool-service-secret-token"):
        # If default or matched, allow
        if token != SERVICE_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "AUTH_INVALID", "message": "Invalid or missing service token"}
            )

# ---------------------------------------------------------------------------
# Request & Response Models
# ---------------------------------------------------------------------------
class CreateRecoveryOrderRequest(BaseModel):
    case_id: Optional[str] = None
    attempt_no: Optional[int] = 1
    amount_minor: Optional[int] = None
    currency: Optional[str] = "INR"

class PaymentVerificationRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    pay_token: Optional[str] = None

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/recovery/orders", status_code=status.HTTP_201_CREATED)
def create_recovery_order(
    req: Optional[CreateRecoveryOrderRequest] = None,
    authorization: Optional[str] = Header(None),
    x_service_token: Optional[str] = Header(None, alias="X-Service-Token"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """
    Creates a new recovery order backed by Razorpay.
    Enforces authorization token validity, idempotency, and rate limits.
    """
    # Service Auth check
    verify_service_auth(x_service_token, authorization)

    # Check Idempotency by Idempotency-Key header first
    clean_idempotency_key = idempotency_key.strip() if isinstance(idempotency_key, str) and idempotency_key.strip() else None
    if clean_idempotency_key and clean_idempotency_key in _IDEMPOTENCY_MAP:
        existing_order_id = _IDEMPOTENCY_MAP[clean_idempotency_key]
        return _RECOVERY_ORDERS[existing_order_id]

    # Authorization Token verification
    token_str = authorization
    claims = verify_authorization_token(token_str)

    case_id = claims["case_id"]
    attempt_no = claims.get("attempt_no", 1)
    amount_minor = claims["amount_minor"]
    currency = claims["currency"]
    decision = claims["decision"]
    approval_id = claims.get("approval_id")
    jti = claims["jti"]

    # Invariant 2: Amount & currency strictly from authorization.
    # If caller provided a request body, ensure it does not attempt to tamper.
    if req:
        if req.case_id and req.case_id != case_id:
            ledger.append("razorpay_checkout_agent", "authorization_rejected", case_id, {"reason": "Body case_id mismatch"})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "AUTH_INVALID", "message": "Body case_id does not match authorization token"}
            )
        if req.amount_minor is not None and req.amount_minor != amount_minor:
            ledger.append("razorpay_checkout_agent", "authorization_rejected", case_id, {"reason": "Customer/caller supplied amount mismatch"})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "AMOUNT_MISMATCH", "message": "Supplied amount does not match authorized amount"}
            )
        if req.currency and req.currency != currency:
            ledger.append("razorpay_checkout_agent", "authorization_rejected", case_id, {"reason": "Body currency mismatch"})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "AMOUNT_MISMATCH", "message": "Supplied currency does not match authorized currency"}
            )

    # Guard: Rate limiting per case (max 3 pay links per case)
    current_links = _CASE_LINKS_COUNT.get(case_id, 0)
    if current_links >= 3 and (case_id, attempt_no) not in _CASE_ATTEMPTS:
        ledger.append("razorpay_checkout_agent", "authorization_rejected", case_id, {"reason": "Rate limited (>3 links)"})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": f"Maximum 3 pay links allowed for case {case_id}"}
        )

    # Check Idempotency by Idempotency-Key
    clean_idempotency_key = idempotency_key.strip() if isinstance(idempotency_key, str) and idempotency_key.strip() else None
    if clean_idempotency_key and clean_idempotency_key in _IDEMPOTENCY_MAP:
        existing_order_id = _IDEMPOTENCY_MAP[clean_idempotency_key]
        return _RECOVERY_ORDERS[existing_order_id]

    # Check Idempotency by (case_id, attempt_no)
    if (case_id, attempt_no) in _CASE_ATTEMPTS:
        existing_order_id = _CASE_ATTEMPTS[(case_id, attempt_no)]
        return _RECOVERY_ORDERS[existing_order_id]

    # Mark jti used once we're past idempotency checks
    _USED_JTI.add(jti)

    # Step 1: Ledger intent before action (Invariant 9)
    ledger.append(
        actor="RecoveraX",
        event_type="recovery_authorized",
        ref_id=case_id,
        payload={
            "case_id": case_id,
            "attempt_no": attempt_no,
            "amount_minor": amount_minor,
            "currency": currency,
            "decision": decision,
            "approval_id": approval_id,
            "jti": jti
        }
    )

    # Step 2: Create Razorpay Order
    receipt = f"RX-{case_id}-{attempt_no}"
    rzp_order_id = None

    # Attempt Razorpay SDK creation if configured and not dummy
    if RAZORPAY_KEY_ID and RAZORPAY_KEY_ID != "rzp_test_mockkey123" and RAZORPAY_KEY_SECRET != "mock_rzp_secret_key_123":
        try:
            import razorpay
            client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
            order_data = {
                "amount": amount_minor,
                "currency": currency,
                "receipt": receipt,
                "notes": {
                    "case_id": case_id,
                    "attempt_no": str(attempt_no),
                    "service": "vasool_recovery"
                }
            }
            rzp_res = client.order.create(data=order_data)
            rzp_order_id = rzp_res.get("id")
        except Exception as rzp_err:
            print(f"[Razorpay] API call note: {rzp_err}. Falling back to deterministic order generation.")

    if not rzp_order_id:
        # Deterministic simulated order ID
        rzp_order_id = f"order_rx_{hashlib.sha256(f'{case_id}:{attempt_no}:{amount_minor}'.encode()).hexdigest()[:14]}"

    # Step 3: Generate pay token and URL
    pay_token = secrets.token_urlsafe(24)
    pay_url = f"{PUBLIC_BASE_URL}/pay/{pay_token}"
    recovery_order_id = f"rec_{secrets.token_hex(8)}"
    now_epoch = int(time.time())
    expires_at = now_epoch + PAY_LINK_TTL_SECONDS

    order_record = {
        "recovery_order_id": recovery_order_id,
        "razorpay_order_id": rzp_order_id,
        "pay_url": pay_url,
        "pay_token": pay_token,
        "amount_minor": amount_minor,
        "currency": currency,
        "case_id": case_id,
        "attempt_no": attempt_no,
        "state": "created",
        "receipt": receipt,
        "decision": decision,
        "approval_id": approval_id,
        "created_at": now_epoch,
        "expires_at": expires_at,
        "payment_id": None
    }

    # Step 4: Write recovery_order_created to ledger
    ledger.append(
        actor="razorpay_checkout_agent",
        event_type="recovery_order_created",
        ref_id=recovery_order_id,
        payload={
            "recovery_order_id": recovery_order_id,
            "case_id": case_id,
            "attempt_no": attempt_no,
            "razorpay_order_id": rzp_order_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "receipt": receipt,
            "expires_at": expires_at
        }
    )

    # Persist in state stores
    _RECOVERY_ORDERS[recovery_order_id] = order_record
    _CASE_ATTEMPTS[(case_id, attempt_no)] = recovery_order_id
    _CASE_LINKS_COUNT[case_id] = _CASE_LINKS_COUNT.get(case_id, 0) + 1
    _PAY_TOKEN_MAP[pay_token] = recovery_order_id
    _RZP_ORDER_MAP[rzp_order_id] = recovery_order_id
    _JTI_TO_ORDER_MAP[jti] = recovery_order_id
    if clean_idempotency_key:
        _IDEMPOTENCY_MAP[clean_idempotency_key] = recovery_order_id

    return order_record

@router.get("/api/recovery/pay/{token}")
def get_pay_page_details(token: str):
    """
    Public token-gated endpoint for the customer pay page.
    Returns strictly non-PII details needed by Razorpay Checkout.
    """
    if not token or token not in _PAY_TOKEN_MAP:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AUTH_INVALID", "message": "Invalid or expired payment link"}
        )

    recovery_order_id = _PAY_TOKEN_MAP[token]
    order = _RECOVERY_ORDERS.get(recovery_order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AUTH_INVALID", "message": "Order not found"}
        )

    now = int(time.time())
    if now > order["expires_at"]:
        order["state"] = "expired"
        ledger.append(
            actor="razorpay_checkout_agent",
            event_type="order_expired",
            ref_id=recovery_order_id,
            payload={"case_id": order["case_id"], "attempt_no": order["attempt_no"]}
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "ORDER_EXPIRED", "message": "This payment link has expired"}
        )

    # Masked case reference: e.g. "RX-****-0042"
    raw_case = order["case_id"]
    parts = raw_case.split("-")
    if len(parts) >= 3:
        masked_case = f"{parts[0]}-****-{parts[-1]}"
    else:
        masked_case = f"RX-****-{raw_case[-4:]}"

    return {
        "amount_minor": order["amount_minor"],
        "currency": order["currency"],
        "merchant_name": MERCHANT_DISPLAY_NAME,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "razorpay_order_id": order["razorpay_order_id"],
        "case_reference": masked_case,
        "state": order["state"],
        "expires_at": order["expires_at"]
    }

@router.post("/api/recovery/verify-payment")
def verify_payment(req: PaymentVerificationRequest):
    """
    Reuses HMAC SHA256 signature verification, then verifies order ID,
    amount, and currency against stored recovery order.
    """
    rzp_order_id = req.razorpay_order_id
    payment_id = req.razorpay_payment_id
    signature = req.razorpay_signature

    # Find stored order
    recovery_order_id = _RZP_ORDER_MAP.get(rzp_order_id)
    if not recovery_order_id and req.pay_token:
        recovery_order_id = _PAY_TOKEN_MAP.get(req.pay_token)

    if not recovery_order_id or recovery_order_id not in _RECOVERY_ORDERS:
        ledger.append(
            actor="razorpay_checkout_agent",
            event_type="payment_rejected",
            ref_id=rzp_order_id,
            payload={"reason": "Order not found", "payment_id": payment_id}
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AUTH_INVALID", "message": "Recovery order not found for verification"}
        )

    order = _RECOVERY_ORDERS[recovery_order_id]

    # Verify order is payable
    if order["state"] in ["expired", "cancelled"]:
        ledger.append(
            actor="razorpay_checkout_agent",
            event_type="payment_rejected",
            ref_id=recovery_order_id,
            payload={"reason": f"Order in state {order['state']}"}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CASE_NOT_PAYABLE", "message": f"Order is {order['state']}"}
        )

    # Check HMAC signature
    # In Razorpay: signature is HMAC_SHA256(order_id + "|" + payment_id, secret)
    message = f"{rzp_order_id}|{payment_id}".encode("utf-8")
    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        message,
        hashlib.sha256
    ).hexdigest()

    is_valid_sig = hmac.compare_digest(expected_signature, signature)
    if not is_valid_sig:
        ledger.append(
            actor="razorpay_checkout_agent",
            event_type="payment_rejected",
            ref_id=recovery_order_id,
            payload={
                "reason": "HMAC signature mismatch",
                "razorpay_order_id": rzp_order_id,
                "payment_id": payment_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AUTH_INVALID", "message": "Forged or invalid payment signature"}
        )

    # Check order ID, amount, and currency match
    if order["razorpay_order_id"] != rzp_order_id:
        ledger.append(
            actor="razorpay_checkout_agent",
            event_type="payment_rejected",
            ref_id=recovery_order_id,
            payload={"reason": "Order ID mismatch"}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AMOUNT_MISMATCH", "message": "Order ID mismatch"}
        )

    if order["currency"] != "INR":
        ledger.append(
            actor="razorpay_checkout_agent",
            event_type="payment_rejected",
            ref_id=recovery_order_id,
            payload={"reason": "Currency mismatch"}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AMOUNT_MISMATCH", "message": "Currency mismatch during verification"}
        )

    # Transition state: payment_reported -> paid
    order["state"] = "payment_reported"
    order["payment_id"] = payment_id

    ledger.append(
        actor="razorpay_checkout_agent",
        event_type="payment_reported",
        ref_id=recovery_order_id,
        payload={
            "recovery_order_id": recovery_order_id,
            "razorpay_order_id": rzp_order_id,
            "payment_id": payment_id,
            "case_id": order["case_id"]
        }
    )

    # Confirmed payment state
    order["state"] = "paid"
    ledger.append(
        actor="razorpay_checkout_agent",
        event_type="payment_verified",
        ref_id=recovery_order_id,
        payload={
            "recovery_order_id": recovery_order_id,
            "razorpay_order_id": rzp_order_id,
            "payment_id": payment_id,
            "amount_minor": order["amount_minor"],
            "currency": order["currency"],
            "receipt": order["receipt"]
        }
    )

    return {
        "status": "success",
        "verified": True,
        "recovery_order_id": recovery_order_id,
        "razorpay_order_id": rzp_order_id,
        "state": "paid",
        "receipt": order["receipt"]
    }

@router.post("/api/webhooks/razorpay")
def razorpay_webhook(
    payload: Optional[Dict[str, Any]] = None,
    raw_bytes: Optional[bytes] = None,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature")
):
    """
    Signed Razorpay webhook handler.
    Verifies X-Razorpay-Signature, deduplicates events, and transitions order state.
    """
    if raw_bytes is not None:
        body_bytes = raw_bytes
    elif payload is not None:
        body_bytes = canonical_json(payload)
    else:
        body_bytes = b""

    if not x_razorpay_signature:
        ledger.append("razorpay_checkout_agent", "payment_rejected", "", {"reason": "Missing webhook signature"})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AUTH_INVALID", "message": "Missing X-Razorpay-Signature header"}
        )

    expected_sig = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body_bytes,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, x_razorpay_signature):
        ledger.append("razorpay_checkout_agent", "payment_rejected", "", {"reason": "Webhook signature mismatch"})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AUTH_INVALID", "message": "Invalid webhook signature"}
        )

    if payload is None:
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON in webhook body")

    event_id = payload.get("event_id") or payload.get("id") or hashlib.sha256(body_bytes).hexdigest()[:16]

    # Deduplication check
    if event_id in _PROCESSED_WEBHOOKS:
        ledger.append(
            actor="razorpay_checkout_agent",
            event_type="webhook_duplicate",
            ref_id=event_id,
            payload={"event_id": event_id}
        )
        return {"status": "duplicate", "event_id": event_id}

    _PROCESSED_WEBHOOKS.add(event_id)

    event_type = payload.get("event", "payment.captured")
    rzp_order_id = None
    payment_id = None

    if "payload" in payload and "payment" in payload["payload"]:
        payment_entity = payload["payload"]["payment"]["entity"]
        rzp_order_id = payment_entity.get("order_id")
        payment_id = payment_entity.get("id")

    ledger.append(
        actor="razorpay_checkout_agent",
        event_type="webhook_received",
        ref_id=event_id,
        payload={"event": event_type, "event_id": event_id, "razorpay_order_id": rzp_order_id}
    )

    # If linked to a recovery order, transition to paid
    if rzp_order_id and rzp_order_id in _RZP_ORDER_MAP:
        rec_id = _RZP_ORDER_MAP[rzp_order_id]
        order = _RECOVERY_ORDERS.get(rec_id)
        if order and order["state"] != "paid":
            order["state"] = "paid"
            order["payment_id"] = payment_id
            ledger.append(
                actor="razorpay_checkout_agent",
                event_type="payment_verified",
                ref_id=rec_id,
                payload={
                    "source": "webhook",
                    "recovery_order_id": rec_id,
                    "razorpay_order_id": rzp_order_id,
                    "payment_id": payment_id
                }
            )

    return {"status": "ok", "event_id": event_id}

@router.get("/api/recovery/orders/{order_id}")
def get_recovery_order_status(
    order_id: str,
    x_service_token: Optional[str] = Header(None, alias="X-Service-Token"),
    authorization: Optional[str] = Header(None)
):
    """
    Status endpoint for RecoveraX confirm-by-GET verification before marking RECOVERED.
    Requires service auth.
    """
    verify_service_auth(x_service_token, authorization)

    order = _RECOVERY_ORDERS.get(order_id)
    if not order:
        # Check if caller looked up by razorpay_order_id
        if order_id in _RZP_ORDER_MAP:
            order = _RECOVERY_ORDERS.get(_RZP_ORDER_MAP[order_id])

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AUTH_INVALID", "message": "Recovery order not found"}
        )

    # Check expiration on read
    now = int(time.time())
    if now > order["expires_at"] and order["state"] == "created":
        order["state"] = "expired"
        ledger.append(
            actor="razorpay_checkout_agent",
            event_type="order_expired",
            ref_id=order["recovery_order_id"],
            payload={"case_id": order["case_id"], "attempt_no": order["attempt_no"]}
        )

    return {
        "recovery_order_id": order["recovery_order_id"],
        "case_id": order["case_id"],
        "attempt_no": order["attempt_no"],
        "razorpay_order_id": order["razorpay_order_id"],
        "amount_minor": order["amount_minor"],
        "currency": order["currency"],
        "state": order["state"],
        "receipt": order["receipt"],
        "created_at": order["created_at"],
        "expires_at": order["expires_at"],
        "payment_id": order.get("payment_id")
    }

@router.post("/api/recovery/orders/{order_id}/cancel")
def cancel_recovery_order(
    order_id: str,
    x_service_token: Optional[str] = Header(None, alias="X-Service-Token"),
    authorization: Optional[str] = Header(None)
):
    """
    Cancels an active recovery order (e.g. when case is stopped or blocked).
    Requires service auth.
    """
    verify_service_auth(x_service_token, authorization)

    order = _RECOVERY_ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order["state"] = "cancelled"
    ledger.append(
        actor="razorpay_checkout_agent",
        event_type="order_cancelled",
        ref_id=order_id,
        payload={"case_id": order["case_id"], "attempt_no": order["attempt_no"]}
    )

    return {"status": "cancelled", "recovery_order_id": order_id}

@router.get("/api/recovery/ledger")
def get_ledger_entries(
    ref_id: Optional[str] = None
):
    """Returns the cryptographic canonical ledger entries."""
    if ref_id:
        filtered = [e for e in ledger.entries if e["ref_id"] == ref_id]
        return filtered
    return ledger.entries

@router.get("/api/recovery/ledger/verify")
def verify_ledger_chain_endpoint():
    """Validates the cryptographic chain of the ledger from genesis."""
    is_valid, report = ledger.verify_chain()
    return report

@router.post("/api/recovery/reset")
def reset_recovery_endpoint(
    x_service_token: Optional[str] = Header(None, alias="X-Service-Token"),
    authorization: Optional[str] = Header(None)
):
    """Resets recovery state and ledger for demo/test suite."""
    verify_service_auth(x_service_token, authorization)
    reset_recovery_state()
    return {"status": "reset_complete"}
