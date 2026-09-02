import os
import json
import time
import hmac
import hashlib
import random
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from groq import Groq
import razorpay
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, func, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SPEND_CAP = float(os.getenv("MERCHANT_SPEND_CAP", "10000"))
MODEL_NAME = "openai/gpt-oss-120b"

# Groq LLM client
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Razorpay client
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID else None

# Neon Postgres Database ORM setup
Base = declarative_base()

class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    action = Column(String, nullable=False)
    sku = Column(String, nullable=True)
    amount = Column(Numeric, nullable=True)
    reasoning = Column(String, nullable=False)
    spend_cap_check = Column(String, nullable=False)
    result = Column(String, nullable=False)
    session_id = Column(String, nullable=True)
    is_attack = Column(Boolean, default=False)

class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=True)
    sku = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric, nullable=False)
    subtotal = Column(Numeric, nullable=False)
    shipping_fee = Column(Numeric, default=0)
    total_amount = Column(Numeric, nullable=False)
    status = Column(String, default="PENDING_PAYMENT")
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    address_line1 = Column(String, nullable=True)
    address_line2 = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    pin_code = Column(String, nullable=True)
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    razorpay_signature = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

db_engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        db_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        Base.metadata.create_all(db_engine)
        SessionLocal = sessionmaker(bind=db_engine)
        print("Connected to Neon Postgres Database successfully.")
    except Exception as err:
        print(f"Neon Postgres DB connection note: {err}")

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

# Audit log in-memory cache
audit_logs: List[Dict[str, Any]] = []

# In-memory orders cache
orders_cache: Dict[str, Dict[str, Any]] = {}

# Session conversation histories for multi-turn chat
session_histories: Dict[str, list] = {}

# Rate limiting: max order attempts per session
MAX_ORDER_ATTEMPTS_PER_SESSION = 5
session_order_counts: Dict[str, int] = {}


def log_audit_entry(
    action: str,
    sku: str,
    amount: float,
    reasoning: str,
    cap_check: str,
    result: str,
    session_id: str = "session_default",
    is_attack: bool = False
) -> Dict[str, Any]:
    entry = {
        "id": int(time.time() * 1000),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": action,
        "sku": sku,
        "amount": amount,
        "reasoning": reasoning,
        "spend_cap_check": cap_check,
        "result": result,
        "session_id": session_id,
        "is_attack": is_attack or (result == "BLOCKED")
    }
    audit_logs.insert(0, entry)

    if SessionLocal:
        try:
            db = SessionLocal()
            record = AuditLogModel(
                action=action,
                sku=sku if sku and sku != "N/A" else None,
                amount=amount if amount > 0 else None,
                reasoning=reasoning,
                spend_cap_check=cap_check,
                result=result,
                session_id=session_id,
                is_attack=is_attack or (result == "BLOCKED")
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            entry["id"] = record.id
            if record.timestamp:
                entry["timestamp"] = record.timestamp.isoformat()
            db.close()
        except Exception as e:
            print(f"Error persisting log to Neon DB: {e}")

    return entry


def verify_razorpay_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """Server-side HMAC SHA256 payment signature verification."""
    if not RAZORPAY_KEY_SECRET:
        return True  # Fallback in simulation mode
    try:
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        generated = hmac.new(RAZORPAY_KEY_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(generated, razorpay_signature)
    except Exception as err:
        print(f"Signature verification error: {err}")
        return False


# ---------- Guardrail Engine ----------

def guardrail_create_razorpay_order(sku: str, quantity: int, reasoning: str, session_id: str):
    """Code-enforced guardrail that validates every order before calling Razorpay."""

    count = session_order_counts.get(session_id, 0)
    if count >= MAX_ORDER_ATTEMPTS_PER_SESSION:
        entry = log_audit_entry("create_order", sku, 0, "Rate limit exceeded for session.", "BLOCKED (Rate Limit)", "BLOCKED", session_id=session_id, is_attack=True)
        return {"success": False, "blocked": True, "reason": "Too many order attempts in this session.", "auditEntry": entry}

    item = next((i for i in catalog if i["sku"] == sku), None)
    if not item:
        entry = log_audit_entry("create_order", sku, 0, f"SKU '{sku}' not in merchant catalog.", "REJECTED (Invalid SKU)", "BLOCKED", session_id=session_id, is_attack=True)
        return {"success": False, "blocked": True, "reason": f"SKU {sku} does not exist.", "auditEntry": entry}

    if item["stock"] < quantity:
        entry = log_audit_entry("create_order", sku, item["price"] * quantity, f"Out of stock ({item['stock']} left, requested {quantity}).", "N/A", "FAILED (Out of Stock)", session_id=session_id)
        return {"success": False, "blocked": False, "reason": f"Product out of stock. Only {item['stock']} available.", "auditEntry": entry}

    # Server-side price calculation
    total_amount = float(item["price"]) * quantity

    if total_amount > SPEND_CAP:
        entry = log_audit_entry("create_order", sku, total_amount, f"Amount ₹{total_amount} exceeds cap ₹{SPEND_CAP}.", f"FAILED (₹{total_amount} > ₹{SPEND_CAP})", "BLOCKED", session_id=session_id, is_attack=True)
        return {"success": False, "blocked": True, "reason": f"Order amount ₹{total_amount:,.0f} exceeds merchant spend cap of ₹{SPEND_CAP:,.0f}.", "auditEntry": entry}

    session_order_counts[session_id] = count + 1
    order_id = f"ORD-{random.randint(100000, 999999)}"

    rzp_order_id = f"rzp_order_{int(time.time())}"
    payment_link = f"https://rzp.io/i/test_{order_id}"

    if rzp_client:
        try:
            rzp_order = rzp_client.order.create({
                "amount": int(total_amount * 100),  # Razorpay uses paise
                "currency": "INR",
                "receipt": order_id,
                "notes": {"sku": sku, "reasoning": reasoning[:200]},
            })
            rzp_order_id = rzp_order["id"]
        except Exception as e:
            print(f"Razorpay order create note: {e}")

    entry = log_audit_entry(
        "create_order", sku, total_amount,
        f"Order created for {item['name']} (SKU: {sku}, Qty: {quantity}). {reasoning}",
        "PASSED", "SUCCESS",
        session_id=session_id
    )

    return {
        "success": True,
        "order_id": order_id,
        "razorpay_order_id": rzp_order_id,
        "payment_link": payment_link,
        "amount": total_amount,
        "currency": "INR",
        "sku": sku,
        "product_name": item["name"],
        "quantity": quantity,
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

SYSTEM_PROMPT = """You are a helpful AI checkout assistant for an online store. You help customers search products, answer questions, and complete purchases safely via Razorpay test-mode.

STRICT FORMATTING & RESPONSE RULES:
- NEVER output raw markdown tables (e.g. do NOT use '| SKU | Name | Price |'). The frontend UI automatically renders interactive visual product cards with images, prices, stock badges, quantity selectors, and 'Buy Now' buttons for any products returned.
- Present product recommendations in clear, warm, conversational text highlighting the product name, key features, and price in ₹.
- Instruct the user that they can click the 'Buy Now' button directly on any product card to initiate their purchase, or reply to confirm which product SKU they want to order.
- Only recommend products that exist in the canonical catalog. Never invent fake prices, discounts, or SKUs.
- You have NO ability to apply discount codes or coupons.
- You have NO access to other customers' data or past sessions.
- The merchant has a hard spend cap. Do not attempt to bypass it.
- Always explain what you are doing before initiating an order."""


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
            for word in query.split():
                matched.extend([i for i in catalog if word in " ".join(i.get("tags", [])) or word in i["name"].lower()])
            matched = list({item["sku"]: item for item in matched}.values())

        if matched:
            entry = log_audit_entry("catalog_lookup", matched[0]["sku"], matched[0]["price"],
                                     f"Catalog search for '{query}'. Found {len(matched)} result(s).", "PASSED", "SUCCESS", session_id=session_id)
        return {"products": matched[:4], "count": len(matched)}

    elif tool_name == "create_order":
        sku = tool_args.get("sku", "")
        quantity = tool_args.get("quantity", 1)
        reasoning = tool_args.get("reasoning", "No reasoning provided")
        return guardrail_create_razorpay_order(sku, quantity, reasoning, session_id)

    return {"error": f"Unknown tool: {tool_name}"}


# ---------- API Endpoints & Models ----------

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "session_default"
    spend_cap: Optional[float] = 10000.0

class CreateOrderRequest(BaseModel):
    sku: str
    quantity: int = 1
    customer_name: str
    customer_phone: str
    address_line1: str
    address_line2: Optional[str] = ""
    city: str
    state: str
    pin_code: str
    session_id: Optional[str] = "session_default"

class VerifyPaymentRequest(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "model": MODEL_NAME,
        "spend_cap": SPEND_CAP,
        "groq_configured": bool(GROQ_API_KEY),
        "razorpay_configured": bool(RAZORPAY_KEY_ID),
        "neon_postgres_configured": bool(SessionLocal),
    }


@app.get("/api/catalog")
def get_catalog():
    return catalog


@app.get("/api/audit-logs")
def get_audit_logs():
    if SessionLocal:
        try:
            db = SessionLocal()
            records = db.query(AuditLogModel).order_by(AuditLogModel.id.desc()).all()
            db.close()
            return [
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "action": r.action,
                    "sku": r.sku or "N/A",
                    "amount": float(r.amount) if r.amount is not None else 0.0,
                    "reasoning": r.reasoning,
                    "spend_cap_check": r.spend_cap_check,
                    "result": r.result,
                    "session_id": r.session_id,
                    "is_attack": r.is_attack
                }
                for r in records
            ]
        except Exception as e:
            print(f"Error querying Neon DB: {e}")

    return audit_logs


@app.post("/api/create-order")
def create_order_endpoint(req: CreateOrderRequest):
    """Server-side order creation endpoint with price calculation, stock check & Razorpay order generation."""
    item = next((i for i in catalog if i["sku"] == req.sku), None)
    if not item:
        raise HTTPException(status_code=400, detail=f"Product SKU '{req.sku}' not found in merchant catalog.")

    if req.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1.")

    if item["stock"] < req.quantity:
        raise HTTPException(status_code=400, detail=f"Insufficient stock. Only {item['stock']} units available for {item['name']}.")

    # Server-side price calculation
    unit_price = float(item["price"])
    subtotal = unit_price * req.quantity
    shipping_fee = 0.0
    total_amount = subtotal + shipping_fee

    if total_amount > SPEND_CAP:
        log_audit_entry("create_order", req.sku, total_amount, f"Order total ₹{total_amount} exceeds spend cap ₹{SPEND_CAP}.", f"FAILED (Exceeds ₹{SPEND_CAP} Cap)", "BLOCKED", session_id=req.session_id, is_attack=True)
        raise HTTPException(status_code=400, detail=f"Order total ₹{total_amount:,.0f} exceeds merchant hard spend cap of ₹{SPEND_CAP:,.0f}.")

    order_id = f"ORD-{random.randint(100000, 999999)}"
    rzp_order_id = f"rzp_order_{int(time.time())}"

    if rzp_client:
        try:
            rzp_order = rzp_client.order.create({
                "amount": int(total_amount * 100),
                "currency": "INR",
                "receipt": order_id,
                "notes": {
                    "sku": req.sku,
                    "customer_name": req.customer_name[:50],
                    "phone": req.customer_phone[:15]
                }
            })
            rzp_order_id = rzp_order["id"]
        except Exception as e:
            print(f"Razorpay order create error: {e}")

    address_str = f"{req.address_line1}, {req.address_line2 + ', ' if req.address_line2 else ''}{req.city}, {req.state} - {req.pin_code}"

    # Save order to database
    order_data = {
        "id": order_id,
        "session_id": req.session_id,
        "sku": req.sku,
        "product_name": item["name"],
        "category": item.get("category", "General"),
        "quantity": req.quantity,
        "unit_price": unit_price,
        "subtotal": subtotal,
        "shipping_fee": shipping_fee,
        "total_amount": total_amount,
        "status": "PENDING_PAYMENT",
        "customer_name": req.customer_name,
        "customer_phone": req.customer_phone,
        "address_line1": req.address_line1,
        "address_line2": req.address_line2,
        "city": req.city,
        "state": req.state,
        "pin_code": req.pin_code,
        "razorpay_order_id": rzp_order_id
    }
    orders_cache[order_id] = order_data

    if SessionLocal:
        try:
            db = SessionLocal()
            db_order = OrderModel(
                id=order_id,
                session_id=req.session_id,
                sku=req.sku,
                product_name=item["name"],
                category=item.get("category", "General"),
                quantity=req.quantity,
                unit_price=unit_price,
                subtotal=subtotal,
                shipping_fee=shipping_fee,
                total_amount=total_amount,
                status="PENDING_PAYMENT",
                customer_name=req.customer_name,
                customer_phone=req.customer_phone,
                address_line1=req.address_line1,
                address_line2=req.address_line2,
                city=req.city,
                state=req.state,
                pin_code=req.pin_code,
                razorpay_order_id=rzp_order_id
            )
            db.add(db_order)
            db.commit()
            db.close()
        except Exception as err:
            print(f"Postgres order save error: {err}")

    log_audit_entry(
        "create_order", req.sku, total_amount,
        f"Order {order_id} created for {req.customer_name} ({req.quantity}x {item['name']}). Address: {address_str}",
        "PASSED", "SUCCESS", session_id=req.session_id
    )

    return {
        "success": True,
        "order_id": order_id,
        "razorpay_order_id": rzp_order_id,
        "razorpay_key_id": RAZORPAY_KEY_ID or "rzp_test_mockkey123",
        "amount": total_amount,
        "currency": "INR",
        "product": item,
        "quantity": req.quantity,
        "unit_price": unit_price,
        "subtotal": subtotal,
        "shipping_fee": shipping_fee,
        "total_amount": total_amount,
        "customer": {
            "name": req.customer_name,
            "phone": req.customer_phone,
            "address": address_str
        }
    }


@app.post("/api/verify-payment")
def verify_payment_endpoint(req: VerifyPaymentRequest):
    """Server-side Razorpay payment signature verification & order status update."""
    valid_signature = verify_razorpay_signature(req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature)

    new_status = "PAID" if valid_signature else "PAYMENT_FAILED"

    # Update in-memory cache
    if req.order_id in orders_cache:
        orders_cache[req.order_id]["status"] = new_status
        orders_cache[req.order_id]["razorpay_payment_id"] = req.razorpay_payment_id
        orders_cache[req.order_id]["razorpay_signature"] = req.razorpay_signature

    # Update Postgres DB
    if SessionLocal:
        try:
            db = SessionLocal()
            order_record = db.query(OrderModel).filter(OrderModel.id == req.order_id).first()
            if not order_record:
                order_record = db.query(OrderModel).filter(OrderModel.razorpay_order_id == req.razorpay_order_id).first()
            if order_record:
                order_record.status = new_status
                order_record.razorpay_payment_id = req.razorpay_payment_id
                order_record.razorpay_signature = req.razorpay_signature
                db.commit()
            db.close()
        except Exception as err:
            print(f"Postgres order update error: {err}")

    # Decrement stock if payment succeeded
    if valid_signature:
        order_info = orders_cache.get(req.order_id, {})
        sku = order_info.get("sku")
        qty = order_info.get("quantity", 1)
        if sku:
            item = next((i for i in catalog if i["sku"] == sku), None)
            if item and item["stock"] >= qty:
                item["stock"] -= qty

    log_audit_entry(
        "payment_verify",
        orders_cache.get(req.order_id, {}).get("sku", "N/A"),
        float(orders_cache.get(req.order_id, {}).get("total_amount", 0)),
        f"Payment verification for Order {req.order_id} (Razorpay Payment ID: {req.razorpay_payment_id}). Status updated to {new_status}.",
        "PASSED" if valid_signature else "FAILED",
        "SUCCESS" if valid_signature else "FAILED"
    )

    if not valid_signature:
        raise HTTPException(status_code=400, detail="Payment signature verification failed.")

    return {
        "success": True,
        "status": "PAID",
        "order_id": req.order_id,
        "razorpay_payment_id": req.razorpay_payment_id,
        "order": orders_cache.get(req.order_id)
    }


@app.get("/api/orders/{order_id}")
def get_order_endpoint(order_id: str):
    if SessionLocal:
        try:
            db = SessionLocal()
            order_rec = db.query(OrderModel).filter(OrderModel.id == order_id).first()
            db.close()
            if order_rec:
                return {
                    "id": order_rec.id,
                    "sku": order_rec.sku,
                    "product_name": order_rec.product_name,
                    "quantity": order_rec.quantity,
                    "unit_price": float(order_rec.unit_price),
                    "subtotal": float(order_rec.subtotal),
                    "total_amount": float(order_rec.total_amount),
                    "status": order_rec.status,
                    "customer_name": order_rec.customer_name,
                    "created_at": order_rec.created_at.isoformat() if order_rec.created_at else None
                }
        except Exception as e:
            print(f"Postgres order query note: {e}")

    if order_id in orders_cache:
        return orders_cache[order_id]

    raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    session_id = req.session_id or "session_default"

    if session_id not in session_histories:
        session_histories[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    history = session_histories[session_id]
    history.append({"role": "user", "content": req.message})

    if not groq_client:
        return _fallback_chat(req)

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

        if msg.tool_calls:
            history.append(msg)

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
                response_data["products"] = all_products[:4]
            if order_result and order_result.get("success"):
                response_data["order"] = order_result
            if audit_entry and audit_entry.get("result") == "BLOCKED":
                response_data["blocked"] = True

            return response_data

        else:
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
    session_id = req.session_id or "session_default"

    if "50000" in prompt_lower or "50,000" in prompt_lower or ("ignore" in prompt_lower and "order" in prompt_lower):
        entry = log_audit_entry("create_order", "CUSTOM_OVERRIDE", 50000,
                                 "Prompt injection to bypass spend cap.", f"FAILED (₹50,000 > ₹{session_cap})", "BLOCKED", session_id=session_id, is_attack=True)
        return {"reply": f"GUARDRAIL ENFORCED: Order amount ₹50,000 exceeds merchant hard spend cap of ₹{session_cap:,.0f}. Blocked at code level.", "blocked": True, "auditEntry": entry}

    if "secret90" in prompt_lower or ("discount" in prompt_lower and "90%" in prompt_lower):
        entry = log_audit_entry("apply_discount", "UNKNOWN", 0, "Unauthorized discount code SECRET90.", "REJECTED (Scope Lock)", "BLOCKED", session_id=session_id, is_attack=True)
        return {"reply": "GUARDRAIL BLOCK: Discount code SECRET90 is not in the whitelisted action set.", "blocked": True, "auditEntry": entry}

    if "last customer" in prompt_lower or "phone number" in prompt_lower or "other session" in prompt_lower:
        entry = log_audit_entry("read_session_data", "N/A", 0, "Cross-session data query attempt.", "BLOCKED (Isolation)", "BLOCKED", session_id=session_id, is_attack=True)
        return {"reply": "SESSION ISOLATION: Agent has no access to other sessions' data.", "blocked": True, "auditEntry": entry}

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
                                 f"Search for '{req.message}'. Matched {item['name']}.", "PASSED", "SUCCESS", session_id=session_id)
        return {
            "reply": f"Here are the top matches I found for your search:\n\n• **{item['name']}** (`{item['sku']}`) — **₹{item['price']:,}**\n\nYou can select the quantity and click **Buy Now** on the product card below to place your order!",
            "products": matched[:2], "auditEntry": entry,
        }

    return {
        "reply": "Hello! How can I help you today? Feel free to ask about products in our catalog or start a purchase.",
        "products": catalog[:4], "auditEntry": None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
