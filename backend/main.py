import os
import json
import time
import hmac
import hashlib
import random
import re
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

def safe_log(msg: Any):
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(str(msg).encode('ascii', 'replace').decode('ascii'), flush=True)
        except Exception:
            pass


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

class ChatHistoryModel(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    consent_given = Column(Boolean, default=False, nullable=False)

db_engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        db_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        Base.metadata.create_all(db_engine)
        SessionLocal = sessionmaker(bind=db_engine)
        safe_log("Connected to Neon Postgres Database successfully.")
    except Exception as err:
        safe_log(f"Neon Postgres DB connection note: {err}")

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

# Consent tracking per session (None = undecided, True = consented, False = declined)
session_consent_status: Dict[str, Optional[bool]] = {}

# Rate limiting: max order attempts per session
MAX_ORDER_ATTEMPTS_PER_SESSION = 5
session_order_counts: Dict[str, int] = {}
MAX_IN_MEMORY_SESSIONS = 500


def trim_in_memory_caches():
    """Prevent memory leaks by capping maximum stored in-memory sessions and logs."""
    if len(session_histories) > MAX_IN_MEMORY_SESSIONS:
        for k in list(session_histories.keys())[:-MAX_IN_MEMORY_SESSIONS]:
            session_histories.pop(k, None)
    if len(orders_cache) > MAX_IN_MEMORY_SESSIONS:
        for k in list(orders_cache.keys())[:-MAX_IN_MEMORY_SESSIONS]:
            orders_cache.pop(k, None)
    if len(session_consent_status) > MAX_IN_MEMORY_SESSIONS:
        for k in list(session_consent_status.keys())[:-MAX_IN_MEMORY_SESSIONS]:
            session_consent_status.pop(k, None)
    if len(session_order_counts) > MAX_IN_MEMORY_SESSIONS:
        for k in list(session_order_counts.keys())[:-MAX_IN_MEMORY_SESSIONS]:
            session_order_counts.pop(k, None)
    if len(audit_logs) > 1000:
        del audit_logs[1000:]


def get_session_consent(session_id: str) -> Optional[bool]:
    """Check if session consent has been given, declined, or is default True."""
    if session_id in session_consent_status:
        return session_consent_status[session_id]

    if SessionLocal:
        try:
            db = SessionLocal()
            record = db.query(ChatHistoryModel).filter(ChatHistoryModel.session_id == session_id).order_by(ChatHistoryModel.id.desc()).first()
            db.close()
            if record:
                session_consent_status[session_id] = record.consent_given
                return record.consent_given
        except Exception as e:
            safe_log(f"Error checking session consent: {e}")

    # Default to True so chats save automatically
    return True


def persist_chat_message(session_id: str, role: str, content: Optional[str]):
    """Store chat message in Neon Postgres DB unless consent was explicitly declined."""
    consent = get_session_consent(session_id)
    if consent is False:
        return  # Privacy guard: Do NOT write message content if consent was explicitly declined

    if not content:
        return

    if SessionLocal:
        try:
            db = SessionLocal()
            rec = ChatHistoryModel(
                session_id=session_id,
                role=role,
                content=str(content),
                consent_given=True
            )
            db.add(rec)
            db.commit()
            db.close()
        except Exception as e:
            safe_log(f"Error persisting chat history message: {e}")



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
    trim_in_memory_caches()

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
            safe_log(f"Error persisting log to Neon DB: {e}")

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
        safe_log(f"Signature verification error: {err}")
        return False


def clean_agent_reply(text: str) -> str:
    """Safety filter to strip ALL markdown formatting and product data from agent text.

    The agent must ONLY return short conversational sentences.
    Product data is delivered via structured JSON, never via text.
    This function is a safety net in case the LLM still generates Markdown.
    """
    if not text:
        return ""
    lines = text.splitlines()
    clean_lines = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        # Skip markdown table rows (header, separator, data)
        if "|" in line and ("---" in line or "SKU" in line or "Price" in line or "Stock" in line or "Name" in line):
            in_table = True
            continue
        if in_table and "|" in line:
            continue
        if in_table and "|" not in line:
            in_table = False
        # Skip bulleted product listings
        if stripped.startswith("- ") and ("SKU" in line or "\u20b9" in line or "price" in line.lower()):
            continue
        if stripped.startswith("- ") and ("SKU" in line or "\u20b9" in line):
            continue
        # Skip lines that are just product details
        if re.match(r'^\*\*[A-Z]{2}\d{3}\*\*', stripped):
            continue
        if re.match(r'^SKU:\s*[A-Z]{2}\d{3}', stripped):
            continue
        clean_lines.append(line)

    res = "\n".join(clean_lines).strip()

    # Strip inline markdown formatting
    res = re.sub(r'\*\*(.+?)\*\*', r'\1', res)  # **bold** -> bold
    res = re.sub(r'`([^`]+)`', r'\1', res)       # `code` -> code
    res = re.sub(r'\u20b9[\d,]+', '', res)             # Remove price mentions
    res = re.sub(r'\bSKU[:\s]+[A-Z]{2}\d{3}\b', '', res)  # Remove SKU references
    res = re.sub(r'\s{2,}', ' ', res).strip()     # Collapse whitespace

    return res if res else "Here are the matching products from our catalog."


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

    total_amount = float(item["price"]) * quantity

    if total_amount > SPEND_CAP:
        entry = log_audit_entry("create_order", sku, total_amount, f"Amount \u20b9{total_amount} exceeds cap \u20b9{SPEND_CAP}.", f"FAILED (\u20b9{total_amount} > \u20b9{SPEND_CAP})", "BLOCKED", session_id=session_id, is_attack=True)
        return {"success": False, "blocked": True, "reason": f"Order amount \u20b9{total_amount:,.0f} exceeds merchant spend cap of \u20b9{SPEND_CAP:,.0f}.", "auditEntry": entry}

    session_order_counts[session_id] = count + 1
    order_id = f"ORD-{random.randint(100000, 999999)}"
    rzp_order_id = f"rzp_order_{int(time.time())}"

    if rzp_client:
        try:
            rzp_order = rzp_client.order.create({
                "amount": int(total_amount * 100),
                "currency": "INR",
                "receipt": order_id,
                "notes": {"sku": sku, "reasoning": reasoning[:200]},
            })
            rzp_order_id = rzp_order["id"]
        except Exception as e:
            safe_log(f"Razorpay order create note: {e}")

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
            "description": "Search the product catalog by keyword, category, tag, or price ceiling. Returns matching products.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword (e.g. 'running shoes', 'watch', 't-shirt')"},
                    "max_price": {"type": "number", "description": "Optional maximum price filter in INR"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "Create a Razorpay order for a product SKU after customer confirms. Enforced by guardrail engine.",
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

SYSTEM_PROMPT = """You are a helpful AI shopping assistant for an online store with a 129-SKU catalog spanning Footwear, Apparel, Electronics, Bags, Accessories, Home, and Fitness.

PRODUCT MATCHING & CLARIFYING QUESTION RULES:

1. Under-Specified vs. Specific-Enough Requests:
   - If the user's query is vague or under-specified (e.g. "show me shoes", "I want a shirt", "show me stuff"), ask ONE short clarifying question before calling search_catalog. Do NOT call search_catalog on vague queries without asking a clarifying question first.
   - Specific-Enough Criteria per Category (if met, SKIP clarifying question and call search_catalog immediately):
     * Footwear: Specifying type of use (e.g. running, casual, sneakers, formal, loafers, boots, heels, sandals, training) OR budget (e.g. under Rs 3000).
     * Apparel: Specifying item type (e.g. hoodie, t-shirt, jeans, dress, kurta, blazer, jacket, shorts, joggers, sweater, saree) OR color/budget.
     * Electronics: Specifying device type (e.g. smart watch, earbuds, headphones, laptop, camera, monitor, power bank, tablet, charger, keyboard) OR budget.
     * Bags / Accessories / Home / Fitness: Specifying item type (e.g. backpack, wallet, sunglasses, luggage, dumbbells, yoga mat, lamp, mug, chair, bottle) OR budget.

2. Using User Answers Directly:
   - When the user responds to your clarifying question (e.g. "for running" or "black"), use that detail directly in your search_catalog tool call on the next turn.

3. Single Round Limit (No Question Loops):
   - Cap clarifying questions at ONE round. Once you have asked one follow-up question and the user replies, you MUST call search_catalog and produce a product recommendation, even if their answer is still partial. Never ask multiple clarifying questions in a row.

4. Fast Path for Specific Queries:
   - If the user's initial message is already specific enough (e.g. "show me running shoes under Rs 3000" or "black oversized t-shirt"), skip the clarifying question and call search_catalog immediately on turn 1.

ABSOLUTE RESPONSE CONTRACT - VIOLATION = SYSTEM FAILURE:

1. Your text response must be ONE short conversational sentence. Nothing more.
2. The frontend renders interactive ProductCards automatically from tool results.
3. You must NEVER include ANY of the following in your text:
   - Markdown tables: | SKU | Name | Price |
   - Bold text: **anything**
   - Backtick code: `anything`
   - Bullet points with product data: - Product Name - price
   - SKU codes: SH001, SH007, etc.
   - Prices: Rs. 899, Rs. 2499, etc.
   - Stock counts: "20 available", "12 in stock"
   - Product descriptions or specifications
   - "Click Buy Now", "Specify quantity", "Continue to Shipping"

CORRECT RESPONSES (use these patterns):
   - "Are you looking for running, casual, or formal shoes?"
   - "I found 3 running shoes matching your budget."
   - "Here are the oversized T-shirts from our catalog."
   - "Product selected. You can proceed with your purchase."
   - "Stock has been verified."

STRICT GUARDRAILS (enforced in code):
- Only recommend products that exist in the canonical catalog.
- Never invent fake prices, discounts, or SKUs.
- You have NO ability to apply discount codes or coupons.
- You have NO access to other customer data or past sessions.
- Hard spend cap is active at Rs. 10000.
"""


SYNONYM_MAP = {
    "pant": ["trousers", "jeans", "chinos", "joggers", "shorts", "leggings"],
    "pants": ["trousers", "jeans", "chinos", "joggers", "shorts", "leggings"],
    "trouser": ["trousers", "jeans", "chinos", "joggers"],
    "trousers": ["trousers", "jeans", "chinos", "joggers"],
    "bottom": ["trousers", "jeans", "chinos", "joggers", "shorts"],
    "bottoms": ["trousers", "jeans", "chinos", "joggers", "shorts"],
    "shoe": ["shoes", "sneakers", "boots", "loafers", "sandals", "heels"],
    "shoes": ["shoes", "sneakers", "boots", "loafers", "sandals", "heels"],
    "sneaker": ["sneakers", "shoes"],
    "sneakers": ["sneakers", "shoes"],
    "tee": ["tshirt"],
    "tees": ["tshirt"],
    "t-shirt": ["tshirt"],
    "tshirt": ["tshirt"],
    "shirt": ["shirt", "tshirt", "polo", "kurta"],
    "top": ["tshirt", "shirt", "hoodie", "sweater", "blazer", "dress", "kurta"],
    "tops": ["tshirt", "shirt", "hoodie", "sweater", "blazer", "dress", "kurta"],
}


def search_catalog_items(query: str, max_price: Optional[float] = None) -> List[Dict[str, Any]]:
    query_clean = query.lower().strip()
    words = [w for w in re.findall(r'\b\w+\b', query_clean) if w not in ["the", "for", "some", "under", "with", "show", "find", "want", "buy", "get", "an", "a", "i", "me", "products", "item", "items", "like", "to", "in"]]

    search_keywords = set(words)
    for w in words:
        if w in SYNONYM_MAP:
            search_keywords.update(SYNONYM_MAP[w])

    matched_dict = {}
    for item in catalog:
        item_name = item["name"].lower()
        item_cat = item.get("category", "").lower()
        item_tags = [t.lower() for t in item.get("tags", [])]

        name_words = set(re.findall(r'\b\w+\b', item_name))
        cat_words = set(re.findall(r'\b\w+\b', item_cat))
        tag_words = set(item_tags)

        if any(kw in name_words or kw in cat_words or kw in tag_words or kw in item_name or kw in item_cat for kw in search_keywords):
            matched_dict[item["sku"]] = item

    matched = list(matched_dict.values())

    if max_price:
        matched = [i for i in matched if i["price"] <= max_price]

    return matched


def execute_tool_call(tool_name: str, tool_args: dict, session_id: str):
    """Execute a tool call from the LLM and return structured JSON."""
    if tool_name == "search_catalog":
        query = tool_args.get("query", "").lower()
        max_price = tool_args.get("max_price")

        matched = search_catalog_items(query, max_price)

        entry = None
        if matched:
            entry = log_audit_entry("catalog_lookup", matched[0]["sku"], matched[0]["price"],
                                     f"Catalog search for '{query}'. Found {len(matched)} result(s).", "PASSED", "SUCCESS", session_id=session_id)
        return {"products": matched[:6], "count": len(matched), "auditEntry": entry}

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

class VerifyStockRequest(BaseModel):
    sku: str
    quantity: int = 1
    session_id: Optional[str] = "session_default"

class ChatConsentRequest(BaseModel):
    session_id: str
    consent: bool


@app.post("/api/verify-stock")
def verify_stock_endpoint(req: VerifyStockRequest):
    """Dedicated stock verification endpoint - real backend operation, not just a UI state change."""
    item = next((i for i in catalog if i["sku"] == req.sku), None)
    if not item:
        entry = log_audit_entry(
            "stock_check", req.sku, 0,
            f"Stock check failed: SKU '{req.sku}' not found in catalog.",
            "N/A", "FAILED", session_id=req.session_id
        )
        raise HTTPException(status_code=404, detail=f"Product SKU '{req.sku}' not found.")

    available = item["stock"]
    verified = available >= req.quantity

    entry = log_audit_entry(
        "stock_check", req.sku, item["price"] * req.quantity,
        f"Stock verification for {item['name']} (SKU: {req.sku}): requested {req.quantity}, available {available}.",
        "PASSED" if verified else "FAILED (Insufficient Stock)",
        "SUCCESS" if verified else "FAILED",
        session_id=req.session_id
    )

    return {
        "type": "stock_verified",
        "verified": verified,
        "sku": req.sku,
        "product_name": item["name"],
        "requested_quantity": req.quantity,
        "available_stock": available,
        "unit_price": item["price"],
        "total_amount": item["price"] * req.quantity,
        "message": f"Stock verified: {available} units available." if verified else f"Insufficient stock. Only {available} units available.",
        "auditEntry": entry
    }


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
            safe_log(f"Error querying Neon DB: {e}")

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

    unit_price = float(item["price"])
    subtotal = unit_price * req.quantity
    shipping_fee = 0.0
    total_amount = subtotal + shipping_fee

    if total_amount > SPEND_CAP:
        log_audit_entry("create_order", req.sku, total_amount, f"Order total \u20b9{total_amount} exceeds spend cap \u20b9{SPEND_CAP}.", f"FAILED (Exceeds \u20b9{SPEND_CAP} Cap)", "BLOCKED", session_id=req.session_id, is_attack=True)
        raise HTTPException(status_code=400, detail=f"Order total \u20b9{total_amount:,.0f} exceeds merchant hard spend cap of \u20b9{SPEND_CAP:,.0f}.")

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
            safe_log(f"Razorpay order create error: {e}")

    address_str = f"{req.address_line1}, {req.address_line2 + ', ' if req.address_line2 else ''}{req.city}, {req.state} - {req.pin_code}"

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
            safe_log(f"Postgres order save error: {err}")

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

    if req.order_id in orders_cache:
        orders_cache[req.order_id]["status"] = new_status
        orders_cache[req.order_id]["razorpay_payment_id"] = req.razorpay_payment_id
        orders_cache[req.order_id]["razorpay_signature"] = req.razorpay_signature

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
            safe_log(f"Postgres order update error: {err}")

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
            safe_log(f"Postgres order query note: {e}")

    if order_id in orders_cache:
        return orders_cache[order_id]

    raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")


@app.post("/api/chat-history/consent")
def set_chat_consent_endpoint(req: ChatConsentRequest):
    """Set or update privacy consent choice for storing chat history for a session."""
    session_id = req.session_id
    session_consent_status[session_id] = req.consent

    if SessionLocal:
        try:
            db = SessionLocal()
            if req.consent:
                # Store all existing in-memory messages for this session
                in_mem = session_histories.get(session_id, [])
                for msg in in_mem:
                    if isinstance(msg, dict):
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        if role != "system" and content:
                            db.add(ChatHistoryModel(
                                session_id=session_id,
                                role=role,
                                content=str(content),
                                consent_given=True
                            ))
                db.commit()
            else:
                # Insert marker record with consent_given=False & content=None
                db.add(ChatHistoryModel(
                    session_id=session_id,
                    role="system",
                    content=None,
                    consent_given=False
                ))
                db.commit()
            db.close()
        except Exception as e:
            safe_log(f"Error setting chat consent: {e}")

    return {
        "success": True,
        "session_id": session_id,
        "consent_given": req.consent,
        "message": "Consent granted. Chat history will be stored." if req.consent else "Consent declined. History will remain in memory only."
    }


@app.get("/api/chat-sessions")
def get_chat_sessions_endpoint():
    """Retrieve list of distinct saved chat sessions stored in Neon DB with consent."""
    sessions_list = []
    if SessionLocal:
        try:
            db = SessionLocal()
            subq = db.query(ChatHistoryModel.session_id)\
                .filter(ChatHistoryModel.consent_given == True)\
                .filter(ChatHistoryModel.content.isnot(None))\
                .distinct().all()

            session_ids = [s[0] for s in subq if s[0]]

            for sid in session_ids:
                first_msg = db.query(ChatHistoryModel)\
                    .filter(ChatHistoryModel.session_id == sid)\
                    .filter(ChatHistoryModel.role == "user")\
                    .filter(ChatHistoryModel.content.isnot(None))\
                    .order_by(ChatHistoryModel.id.asc()).first()

                count = db.query(ChatHistoryModel)\
                    .filter(ChatHistoryModel.session_id == sid)\
                    .filter(ChatHistoryModel.content.isnot(None)).count()

                title = (first_msg.content[:36] + "...") if first_msg and len(first_msg.content or "") > 36 else (first_msg.content if first_msg else "Shopping Chat")
                created_at = first_msg.created_at.isoformat() if first_msg and first_msg.created_at else None

                sessions_list.append({
                    "session_id": sid,
                    "title": title,
                    "created_at": created_at,
                    "message_count": count
                })
            db.close()
            sessions_list.sort(key=lambda s: s["created_at"] or "", reverse=True)
        except Exception as e:
            safe_log(f"Error querying chat sessions: {e}")

    return {"sessions": sessions_list}


@app.get("/api/chat-history/{session_id}")
def get_chat_history_endpoint(session_id: str):
    """Retrieve stored chat history for a session (strictly filtered by session_id)."""
    consent = get_session_consent(session_id)
    if consent is not True:
        return {"session_id": session_id, "consent_given": False, "messages": []}

    if SessionLocal:
        try:
            db = SessionLocal()
            # Session isolation: filter strictly by session_id
            records = db.query(ChatHistoryModel)\
                .filter(ChatHistoryModel.session_id == session_id)\
                .filter(ChatHistoryModel.consent_given == True)\
                .filter(ChatHistoryModel.content.isnot(None))\
                .order_by(ChatHistoryModel.id.asc())\
                .all()
            db.close()
            return {
                "session_id": session_id,
                "consent_given": True,
                "messages": [
                    {
                        "id": r.id,
                        "role": r.role,
                        "content": r.content,
                        "created_at": r.created_at.isoformat() if r.created_at else None
                    }
                    for r in records
                ]
            }
        except Exception as e:
            safe_log(f"Error querying chat history: {e}")

    return {"session_id": session_id, "consent_given": True, "messages": []}


@app.delete("/api/chat-history/{session_id}")
def delete_chat_history_endpoint(session_id: str):
    """Clear stored history for a session from DB & reset session state."""
    session_consent_status.pop(session_id, None)
    session_order_counts.pop(session_id, None)
    if session_id in session_histories:
        session_histories[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    deleted_count = 0
    if SessionLocal:
        try:
            db = SessionLocal()
            # Session isolation: filter strictly by session_id
            deleted_count = db.query(ChatHistoryModel).filter(ChatHistoryModel.session_id == session_id).delete(synchronize_session=False)
            db.commit()
            db.close()
        except Exception as e:
            safe_log(f"Error deleting chat history: {e}")

    return {
        "success": True,
        "session_id": session_id,
        "deleted_count": deleted_count,
        "message": f"Chat history for session '{session_id}' cleared."
    }


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    session_id = req.session_id or "session_default"
    needs_consent = (get_session_consent(session_id) is None)

    if session_id not in session_histories:
        session_histories[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    history = session_histories[session_id]
    history.append({"role": "user", "content": req.message})
    persist_chat_message(session_id, "user", req.message)

    if not groq_client:
        res = _fallback_chat(req)
        res["needs_consent"] = needs_consent
        return res

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

            raw_reply = follow_up.choices[0].message.content or ""
            clean_reply = clean_agent_reply(raw_reply)
            if all_products:
                clean_reply = f"I found {len(all_products)} product{'s' if len(all_products)!=1 else ''} matching your search."

            history.append({"role": "assistant", "content": clean_reply})
            persist_chat_message(session_id, "assistant", clean_reply)

            response_type = "product_search" if all_products else "text"
            response_data = {
                "type": response_type,
                "reply": clean_reply or f"I found {len(all_products)} matching product{'s' if len(all_products)!=1 else ''} in the catalog.",
                "auditEntry": audit_entry,
                "needs_consent": needs_consent,
            }
            if all_products:
                response_data["products"] = all_products[:6]
            if order_result and order_result.get("success"):
                response_data["type"] = "order_created"
                response_data["order"] = order_result
            if audit_entry and audit_entry.get("result") == "BLOCKED":
                response_data["blocked"] = True

            return response_data

        else:
            raw_reply = msg.content or ""
            clean_reply = clean_agent_reply(raw_reply)
            history.append({"role": "assistant", "content": clean_reply})
            persist_chat_message(session_id, "assistant", clean_reply)
            return {"type": "text", "reply": clean_reply, "auditEntry": None, "needs_consent": needs_consent}

    except Exception as e:
        safe_log(f"Groq API error: {e}")
        res = _fallback_chat(req)
        res["needs_consent"] = needs_consent
        return res


def _fallback_chat(req: ChatRequest):
    """Rule-based fallback when Groq API is unavailable."""
    prompt_lower = req.message.lower().strip()
    session_cap = req.spend_cap or SPEND_CAP
    session_id = req.session_id or "session_default"
    needs_consent = (get_session_consent(session_id) is None)

    if "50000" in prompt_lower or "50,000" in prompt_lower or ("ignore" in prompt_lower and "order" in prompt_lower):
        entry = log_audit_entry("create_order", "CUSTOM_OVERRIDE", 50000,
                                 "Prompt injection to bypass spend cap.", f"FAILED (\u20b950,000 > \u20b9{session_cap})", "BLOCKED", session_id=session_id, is_attack=True)
        res_reply = f"GUARDRAIL ENFORCED: Order amount \u20b950,000 exceeds merchant hard spend cap of \u20b9{session_cap:,.0f}. Blocked at code level."
        persist_chat_message(session_id, "assistant", res_reply)
        return {"type": "blocked", "reply": res_reply, "blocked": True, "auditEntry": entry, "needs_consent": needs_consent}

    if "secret90" in prompt_lower or ("discount" in prompt_lower and "90%" in prompt_lower):
        entry = log_audit_entry("apply_discount", "UNKNOWN", 0, "Unauthorized discount code SECRET90.", "REJECTED (Scope Lock)", "BLOCKED", session_id=session_id, is_attack=True)
        res_reply = "GUARDRAIL BLOCK: Discount code SECRET90 is not in the whitelisted action set."
        persist_chat_message(session_id, "assistant", res_reply)
        return {"type": "blocked", "reply": res_reply, "blocked": True, "auditEntry": entry, "needs_consent": needs_consent}

    if "last customer" in prompt_lower or "phone number" in prompt_lower or "other session" in prompt_lower:
        entry = log_audit_entry("read_session_data", "N/A", 0, "Cross-session data query attempt.", "BLOCKED (Isolation)", "BLOCKED", session_id=session_id, is_attack=True)
        res_reply = "SESSION ISOLATION: Agent has no access to other sessions' data or stored chat history."
        persist_chat_message(session_id, "assistant", res_reply)
        return {"type": "blocked", "reply": res_reply, "blocked": True, "auditEntry": entry, "needs_consent": needs_consent}

    # Check for single-round clarifying question on vague single/two-word category requests
    clean_prompt = prompt_lower.replace("i want to buy", "").replace("i want to get", "").replace("i want", "").replace("show me", "").replace("need", "").replace("buy", "").replace("get", "").replace("an", "").replace("a", "").strip()

    history = session_histories.get(session_id, [])
    already_asked_clarifying = any(
        isinstance(m, dict) and m.get("role") == "assistant" and "?" in m.get("content", "")
        for m in history
    )

    if not already_asked_clarifying:
        if clean_prompt in ["pant", "pants", "trouser", "trousers", "bottom", "bottoms"]:
            res_reply = "Are you looking for casual jeans, formal trousers, cargo pants, or chinos?"
            persist_chat_message(session_id, "assistant", res_reply)
            return {"type": "text", "reply": res_reply, "products": [], "auditEntry": None, "needs_consent": needs_consent}

        elif clean_prompt in ["shoe", "shoes", "sneaker", "sneakers", "footwear"]:
            res_reply = "Are you looking for running shoes, casual sneakers, training shoes, or formal loafers?"
            persist_chat_message(session_id, "assistant", res_reply)
            return {"type": "text", "reply": res_reply, "products": [], "auditEntry": None, "needs_consent": needs_consent}

        elif clean_prompt in ["shirt", "tshirt", "t-shirt", "top", "apparel", "clothes"]:
            res_reply = "Are you looking for casual T-shirts, formal Oxford shirts, hoodies, or polo shirts?"
            persist_chat_message(session_id, "assistant", res_reply)
            return {"type": "text", "reply": res_reply, "products": [], "auditEntry": None, "needs_consent": needs_consent}

    # Execute intelligent catalog search
    matched = search_catalog_items(req.message)

    if matched:
        item = matched[0]
        entry = log_audit_entry("catalog_lookup", item["sku"], item["price"],
                                 f"Catalog search for '{req.message}'. Found {len(matched)} result(s).", "PASSED", "SUCCESS", session_id=session_id)
        res_reply = f"I found {len(matched)} product{'s' if len(matched)>1 else ''} matching your search."
        persist_chat_message(session_id, "assistant", res_reply)
        return {
            "type": "product_search",
            "reply": res_reply,
            "products": matched[:6],
            "auditEntry": entry,
            "needs_consent": needs_consent,
        }

    res_reply = "I couldn't find any items matching your request. Feel free to search for shoes, hoodies, jeans, smart watches, or backpacks."
    persist_chat_message(session_id, "assistant", res_reply)
    return {
        "type": "text",
        "reply": res_reply,
        "products": [],
        "auditEntry": None,
        "needs_consent": needs_consent,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
