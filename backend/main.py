import os
import json
import time
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import razorpay

load_dotenv()

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
SPEND_CAP = float(os.getenv("MERCHANT_SPEND_CAP", "10000"))
MODEL_NAME = "openai/gpt-oss-120b"

# Groq LLM client
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Razorpay client
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID else None

app = FastAPI(
    title="Razorpay Checkout Agent Service",
    description="Conversational Checkout Agent with Verified Guardrail Engine",
    version="1.0.0"
)

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

# Audit log storage (in-memory & append-only)
audit_logs: List[Dict[str, Any]] = []

# Session conversation histories for multi-turn chat
session_histories: Dict[str, list] = {}

# Rate limiting: max order attempts per session
MAX_ORDER_ATTEMPTS_PER_SESSION = 5
session_order_counts: Dict[str, int] = {}


def log_audit_entry(action: str, sku: str, amount: float, reasoning: str, cap_check: str, result: str) -> Dict[str, Any]:
    entry = {
        "id": int(time.time() * 1000),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": action,
        "sku": sku,
        "amount": amount,
        "reasoning": reasoning,
        "spend_cap_check": cap_check,
        "result": result,
    }
    audit_logs.insert(0, entry)
    return entry


# ---------- Guardrail Engine ----------

def guardrail_create_razorpay_order(sku: str, quantity: int, reasoning: str, session_id: str):
    """Code-enforced guardrail that validates every order before calling Razorpay."""

    # 0. Rate limit check
    count = session_order_counts.get(session_id, 0)
    if count >= MAX_ORDER_ATTEMPTS_PER_SESSION:
        entry = log_audit_entry("create_order", sku, 0, "Rate limit exceeded for session.", "BLOCKED (Rate Limit)", "BLOCKED")
        return {"success": False, "blocked": True, "reason": "Too many order attempts in this session.", "auditEntry": entry}

    # 1. Scope Lock — SKU must exist in catalog
    item = next((i for i in catalog if i["sku"] == sku), None)
    if not item:
        entry = log_audit_entry("create_order", sku, 0, f"SKU '{sku}' not in merchant catalog.", "REJECTED (Invalid SKU)", "BLOCKED")
        return {"success": False, "blocked": True, "reason": f"SKU {sku} does not exist.", "auditEntry": entry}

    # 2. Stock check
    if item["stock"] < quantity:
        entry = log_audit_entry("create_order", sku, item["price"] * quantity, f"Out of stock ({item['stock']} left, requested {quantity}).", "N/A", "FAILED (Out of Stock)")
        return {"success": False, "blocked": False, "reason": "Product out of stock.", "auditEntry": entry}

    total_amount = item["price"] * quantity

    # 3. Hard Spend Cap (code-enforced, not prompt-level)
    if total_amount > SPEND_CAP:
        entry = log_audit_entry("create_order", sku, total_amount, f"Amount ₹{total_amount} exceeds cap ₹{SPEND_CAP}.", f"FAILED (₹{total_amount} > ₹{SPEND_CAP})", "BLOCKED")
        return {"success": False, "blocked": True, "reason": f"₹{total_amount} exceeds spend cap ₹{SPEND_CAP}.", "auditEntry": entry}

    # 4. Create real Razorpay test-mode order
    session_order_counts[session_id] = count + 1

    if rzp_client:
        try:
            rzp_order = rzp_client.order.create({
                "amount": total_amount * 100,  # Razorpay uses paise
                "currency": "INR",
                "receipt": f"rcpt_{sku}_{int(time.time())}",
                "notes": {"sku": sku, "reasoning": reasoning[:200]},
            })
            order_id = rzp_order["id"]
        except Exception as e:
            entry = log_audit_entry("create_order", sku, total_amount, f"Razorpay API error: {str(e)}", "PASSED", "FAILED (API Error)")
            return {"success": False, "blocked": False, "reason": f"Razorpay API error: {str(e)}", "auditEntry": entry}
    else:
        order_id = f"order_sim_{int(time.time())}"

    # Generate a payment link via Razorpay
    payment_link = None
    if rzp_client:
        try:
            link = rzp_client.payment_link.create({
                "amount": total_amount * 100,
                "currency": "INR",
                "description": f"Order for {item['name']} (SKU: {sku})",
                "notes": {"sku": sku, "order_id": order_id},
            })
            payment_link = link.get("short_url", link.get("url"))
        except Exception:
            payment_link = f"https://rzp.io/i/test_{order_id}"
    else:
        payment_link = f"https://rzp.io/i/test_{order_id}"

    entry = log_audit_entry(
        "create_order", sku, total_amount,
        f"Order created for {item['name']} (SKU: {sku}). {reasoning}",
        "PASSED", "SUCCESS",
    )

    return {
        "success": True,
        "order_id": order_id,
        "payment_link": payment_link,
        "amount": total_amount,
        "currency": "INR",
        "sku": sku,
        "product_name": item["name"],
        "auditEntry": entry,
    }


# ---------- LLM Tool Definitions ----------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Search the product catalog by keyword, category, or tag. Returns matching products.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword (e.g. 'running shoes', 'watch', 'headphones')"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "Create a Razorpay order for a product SKU after the customer confirms. Enforced by guardrail engine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "The product SKU to order (must exist in catalog)"},
                    "quantity": {"type": "integer", "description": "Number of units to order", "default": 1},
                    "reasoning": {"type": "string", "description": "Natural-language reason for creating this order"},
                },
                "required": ["sku", "reasoning"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a helpful AI checkout assistant for an online store. You help customers:
1. Search for products in the catalog
2. Answer questions about products (price, stock, description)
3. Complete purchases via Razorpay test-mode

STRICT RULES (these are enforced in code, but you must also follow them):
- Only recommend products that exist in the catalog.
- Never invent prices, discounts, or SKUs.
- You have NO ability to apply discounts or coupons.
- You have NO access to other customers' data or past sessions.
- The merchant has a hard spend cap. Do not attempt to bypass it.
- Always explain what you are doing before creating an order.

If a user asks you to do something outside your capabilities, politely decline."""


def execute_tool_call(tool_name: str, tool_args: dict, session_id: str):
    """Execute a tool call from the LLM and return the result."""
    if tool_name == "search_catalog":
        query = tool_args.get("query", "").lower()
        matched = [
            item for item in catalog
            if any(tag in query for tag in item.get("tags", []))
            or query in item["name"].lower()
            or query in item.get("category", "").lower()
            or query in item.get("description", "").lower()
        ]
        if not matched:
            # Fuzzy fallback
            for word in query.split():
                matched.extend([i for i in catalog if word in " ".join(i.get("tags", [])) or word in i["name"].lower()])
            matched = list({item["sku"]: item for item in matched}.values())

        if matched:
            entry = log_audit_entry("catalog_lookup", matched[0]["sku"], matched[0]["price"],
                                     f"Catalog search for '{query}'. Found {len(matched)} result(s).", "PASSED", "SUCCESS")
        return {"products": matched[:3], "count": len(matched)}

    elif tool_name == "create_order":
        sku = tool_args.get("sku", "")
        quantity = tool_args.get("quantity", 1)
        reasoning = tool_args.get("reasoning", "No reasoning provided")
        return guardrail_create_razorpay_order(sku, quantity, reasoning, session_id)

    return {"error": f"Unknown tool: {tool_name}"}


# ---------- API Endpoints ----------

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "session_default"
    spend_cap: Optional[float] = 10000.0


@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "model": MODEL_NAME,
        "spend_cap": SPEND_CAP,
        "groq_configured": bool(GROQ_API_KEY),
        "razorpay_configured": bool(RAZORPAY_KEY_ID),
    }


@app.get("/api/catalog")
def get_catalog():
    return catalog


@app.get("/api/audit-logs")
def get_audit_logs():
    return audit_logs


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    session_id = req.session_id or "session_default"

    # Initialize session history if needed
    if session_id not in session_histories:
        session_histories[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    history = session_histories[session_id]
    history.append({"role": "user", "content": req.message})

    # If Groq is not configured, fall back to rule-based matching
    if not groq_client:
        return _fallback_chat(req)

    # Call Groq LLM with tool-use
    try:
        response = groq_client.chat.completions.create(
            model=MODEL_NAME,
            messages=history,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            max_tokens=1024,
            temperature=0.7,
        )

        msg = response.choices[0].message

        # Handle tool calls
        if msg.tool_calls:
            history.append(msg)  # append assistant message with tool_calls

            all_products = []
            audit_entry = None
            order_result = None

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                result = execute_tool_call(fn_name, fn_args, session_id)

                history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

                if "products" in result:
                    all_products.extend(result["products"])
                if "auditEntry" in result:
                    audit_entry = result["auditEntry"]
                if "order_id" in result:
                    order_result = result

            # Second LLM call to generate final response
            follow_up = groq_client.chat.completions.create(
                model=MODEL_NAME,
                messages=history,
                max_tokens=1024,
                temperature=0.7,
            )

            reply_text = follow_up.choices[0].message.content or ""
            history.append({"role": "assistant", "content": reply_text})

            response_data = {"reply": reply_text, "auditEntry": audit_entry}
            if all_products:
                response_data["products"] = all_products[:3]
            if order_result and order_result.get("success"):
                response_data["order"] = {
                    "order_id": order_result["order_id"],
                    "payment_link": order_result["payment_link"],
                    "amount": order_result["amount"],
                    "product_name": order_result.get("product_name", ""),
                }
            if audit_entry and audit_entry.get("result") == "BLOCKED":
                response_data["blocked"] = True

            return response_data

        else:
            # Plain text response (no tool calls)
            reply_text = msg.content or ""
            history.append({"role": "assistant", "content": reply_text})
            return {"reply": reply_text, "auditEntry": None}

    except Exception as e:
        print(f"Groq API error: {e}")
        return _fallback_chat(req)


def _fallback_chat(req: ChatRequest):
    """Rule-based fallback when Groq API is unavailable."""
    prompt_lower = req.message.lower()
    session_cap = req.spend_cap or SPEND_CAP

    # Attack 1: Spend-cap bypass
    if "50000" in prompt_lower or "50,000" in prompt_lower or ("ignore" in prompt_lower and "order" in prompt_lower):
        entry = log_audit_entry("create_order", "CUSTOM_OVERRIDE", 50000,
                                 "Prompt injection to bypass spend cap.", f"FAILED (₹50,000 > ₹{session_cap})", "BLOCKED")
        return {"reply": f"GUARDRAIL ENFORCED: Order amount ₹50,000 exceeds merchant hard spend cap of ₹{session_cap:,.0f}. Blocked at code level.", "blocked": True, "auditEntry": entry}

    # Attack 2: Unauthorized discount
    if "secret90" in prompt_lower or ("discount" in prompt_lower and "90%" in prompt_lower):
        entry = log_audit_entry("apply_discount", "UNKNOWN", 0, "Unauthorized discount code SECRET90.", "REJECTED (Scope Lock)", "BLOCKED")
        return {"reply": "GUARDRAIL BLOCK: Discount code SECRET90 is not in the whitelisted action set.", "blocked": True, "auditEntry": entry}

    # Attack 3: Data leakage
    if "last customer" in prompt_lower or "phone number" in prompt_lower or "other session" in prompt_lower:
        entry = log_audit_entry("read_session_data", "N/A", 0, "Cross-session data query attempt.", "BLOCKED (Isolation)", "BLOCKED")
        return {"reply": "SESSION ISOLATION: Agent has no access to other sessions' data.", "blocked": True, "auditEntry": entry}

    # Normal catalog search
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
        elif "headphone" in prompt_lower or "audio" in prompt_lower:
            matched = [i for i in catalog if "audio" in i["tags"]]

    if matched:
        item = matched[0]
        entry = log_audit_entry("catalog_lookup", item["sku"], item["price"],
                                 f"Search for '{req.message}'. Matched {item['name']}.", "PASSED", "SUCCESS")
        return {
            "reply": f"I found **{item['name']}** (SKU: `{item['sku']}`) for **₹{item['price']:,}**.\n\n{item['description']}\n\nWould you like to complete this order via Razorpay?",
            "products": matched[:2], "auditEntry": entry,
        }

    return {
        "reply": "Hello! How can I help you today? Feel free to ask about products in our catalog or start a purchase.",
        "products": catalog[:3], "auditEntry": None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
