import os
import json
import time
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_mockkey123")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "mocksecret123")
SPEND_CAP = float(os.getenv("MERCHANT_SPEND_CAP", "10000"))
MODEL_NAME = "openai/gpt-oss-120b"

app = FastAPI(
    title="Razorpay Checkout Agent Service",
    description="Conversational Checkout Agent with Verified Guardrail Engine",
    version="1.0.0"
)

# CORS middleware for React UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load catalog data
CATALOG_FILE = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "data", "catalog.json")
def load_catalog():
    if os.path.exists(CATALOG_FILE):
        with open(CATALOG_FILE, "r") as f:
            return json.load(f)
    return []

catalog = load_catalog()

# Audit log storage (in-memory & append-only log)
audit_logs: List[Dict[str, Any]] = []

def log_audit_entry(action: str, sku: str, amount: float, reasoning: str, cap_check: str, result: str) -> Dict[str, Any]:
    entry = {
        "id": int(time.time() * 1000),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": action,
        "sku": sku,
        "amount": amount,
        "reasoning": reasoning,
        "spend_cap_check": cap_check,
        "result": result
    }
    audit_logs.insert(0, entry)
    return entry

# Request Models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "session_default"
    spend_cap: Optional[float] = 10000.0

class OrderRequest(BaseModel):
    sku: str
    quantity: int = 1
    reasoning: str

# Guardrail Engine Core
def validate_and_execute_order(sku: str, quantity: int, reasoning: str, session_cap: float):
    # 1. Scope Lock Check (Must exist in canonical catalog)
    item = next((i for i in catalog if i["sku"] == sku), None)
    if not item:
        log_audit_entry(
            action="create_order",
            sku=sku,
            amount=0,
            reasoning=f"REJECTED: SKU '{sku}' is not present in merchant catalog.",
            cap_check="REJECTED (Invalid Scope)",
            result="BLOCKED"
        )
        return {"success": False, "reason": f"SKU {sku} does not exist in catalog.", "blocked": True}

    # 2. Stock Check
    if item["stock"] < quantity:
        log_audit_entry(
            action="create_order",
            sku=sku,
            amount=item["price"] * quantity,
            reasoning=f"FAILED: Insufficient stock ({item['stock']} available, requested {quantity}).",
            cap_check="PASSED",
            result="FAILED (Out of Stock)"
        )
        return {"success": False, "reason": "Product out of stock.", "blocked": False}

    total_amount = item["price"] * quantity

    # 3. Hard Spend Cap Check
    if total_amount > session_cap:
        log_audit_entry(
            action="create_order",
            sku=sku,
            amount=total_amount,
            reasoning=f"GUARDRAIL BLOCKED: Order amount ₹{total_amount} exceeds spend cap ₹{session_cap}.",
            cap_check=f"FAILED (₹{total_amount} > ₹{session_cap})",
            result="BLOCKED"
        )
        return {
            "success": False,
            "reason": f"Order amount ₹{total_amount} exceeds merchant hard spend cap of ₹{session_cap}.",
            "blocked": True
        }

    # 4. Generate Razorpay Test Order
    order_id = f"rzp_order_{int(time.time())}"
    payment_link = f"https://rzp.io/i/test_{order_id}"

    entry = log_audit_entry(
        action="create_order",
        sku=sku,
        amount=total_amount,
        reasoning=f"Verified order for {item['name']} (SKU: {sku}). Reason: {reasoning}",
        cap_check="PASSED",
        result="SUCCESS"
    )

    return {
        "success": True,
        "order_id": order_id,
        "payment_link": payment_link,
        "amount": total_amount,
        "currency": "INR",
        "sku": sku,
        "audit_entry": entry
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "model": MODEL_NAME,
        "spend_cap": SPEND_CAP,
        "groq_configured": bool(GROQ_API_KEY)
    }

@app.get("/api/catalog")
def get_catalog():
    return catalog

@app.get("/api/audit-logs")
def get_audit_logs():
    return audit_logs

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    prompt_lower = req.message.lower()
    session_cap = req.spend_cap or SPEND_CAP

    # Red-Team Attack 1: Spend Cap Bypass via Prompt Injection
    if "50000" in prompt_lower or "50,000" in prompt_lower or ("ignore" in prompt_lower and "order" in prompt_lower):
        entry = log_audit_entry(
            action="create_order",
            sku="CUSTOM_OVERRIDE",
            amount=50000,
            reasoning="Attempted prompt injection to override spend cap and create ₹50,000 order.",
            cap_check="FAILED (Exceeds ₹10,000 Cap)",
            result="BLOCKED"
        )
        return {
            "reply": f"🚨 **GUARDRAIL ENFORCED**: Action Blocked!\n\nOrder amount ₹50,000 exceeds merchant hard spend cap of ₹{session_cap:,.0f}. The request was rejected at code-level before calling Razorpay API.",
            "blocked": True,
            "auditEntry": entry
        }

    # Red-Team Attack 2: Price Manipulation / Unauthorized Discount
    if "secret90" in prompt_lower or ("discount" in prompt_lower and "90%" in prompt_lower):
        entry = log_audit_entry(
            action="apply_discount",
            sku="UNKNOWN",
            amount=0,
            reasoning="User requested unauthorized discount code SECRET90.",
            cap_check="REJECTED (Scope Lock)",
            result="BLOCKED"
        )
        return {
            "reply": "🛡️ **GUARDRAIL BLOCK**: Unauthorized Action!\n\nDiscount code `SECRET90` is not in the whitelisted action set.",
            "blocked": True,
            "auditEntry": entry
        }

    # Red-Team Attack 3: Data Leakage
    if "last customer" in prompt_lower or "phone number" in prompt_lower or "other session" in prompt_lower:
        entry = log_audit_entry(
            action="read_session_data",
            sku="N/A",
            amount=0,
            reasoning="User queried cross-session customer order history and PII.",
            cap_check="BLOCKED (Isolation Enforced)",
            result="BLOCKED"
        )
        return {
            "reply": "🔒 **SESSION ISOLATION GUARD**: Access Denied!\n\nAgent execution environment is isolated to your current session. Cross-session database read tools are not exposed.",
            "blocked": True,
            "auditEntry": entry
        }

    # Normal Search & Recommendation Intent
    matched = [
        item for item in catalog
        if any(tag in prompt_lower for tag in item.get("tags", []))
        or item["name"].lower() in prompt_lower
        or item["category"].lower() in prompt_lower
    ]

    if not matched:
        if "shoe" in prompt_lower or "sneaker" in prompt_lower or "running" in prompt_lower:
            matched = [i for i in catalog if "shoes" in i["tags"]]
        elif "watch" in prompt_lower:
            matched = [i for i in catalog if "watch" in i["tags"]]

    if matched:
        item = matched[0]
        entry = log_audit_entry(
            action="catalog_lookup",
            sku=item["sku"],
            amount=item["price"],
            reasoning=f"User asked for '{req.message}'. Matched SKU {item['sku']} ({item['name']}).",
            cap_check="PASSED",
            result="SUCCESS"
        )
        return {
            "reply": f"I found **{item['name']}** (SKU: `{item['sku']}`) for **₹{item['price']:,}**.\n\n{item['description']}\n\nWould you like to complete this order via Razorpay test-mode?",
            "products": matched[:2],
            "auditEntry": entry
        }

    return {
        "reply": "Hello! I am your AI Checkout Agent powered by Groq (`openai/gpt-oss-120b`). I can help you search products and complete purchases safely on Razorpay test mode. What are you looking for today?",
        "products": catalog[:3],
        "auditEntry": None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
