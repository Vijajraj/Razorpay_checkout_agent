# Spec: Today's Build — Neon DB Migration + Catalog Images

**Scope for today:** Move audit logging to Neon Postgres, add product images to the catalog. Tier 1 (4th attack, metrics) and Tier 2 (deploy, latency) are deferred to tomorrow. No changes to guardrail logic, agent code, or the Razorpay integration.
**Budget:** ~4-5 hours total.

---

## Part A — Neon Postgres Migration for Audit Log (~3-4 hrs)

### A1. Goal
Replace the JSON-file audit log with a real, queryable Postgres table on Neon. Storage-layer swap only — schema and guardrail logic stay identical.

### A2. Setup
1. Create a free Neon project at neon.tech (no credit card needed on free tier).
2. Copy the connection string: `postgresql://user:password@host/dbname?sslmode=require`.
3. Add to `backend/.env` as `DATABASE_URL=...` — confirm `.env` stays in `.gitignore`.
4. Install: `pip install sqlalchemy psycopg2-binary`.

### A3. Schema (mirrors existing JSON fields, adds two cheap extras for later metrics)
```sql
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    action TEXT NOT NULL,
    sku TEXT,
    amount NUMERIC,
    reasoning TEXT NOT NULL,
    spend_cap_check TEXT NOT NULL,
    result TEXT NOT NULL,
    session_id TEXT,
    is_attack BOOLEAN DEFAULT FALSE
);
```

### A4. SQLAlchemy Model
```python
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    action = Column(String, nullable=False)
    sku = Column(String, nullable=True)
    amount = Column(Numeric, nullable=True)
    reasoning = Column(String, nullable=False)
    spend_cap_check = Column(String, nullable=False)
    result = Column(String, nullable=False)
    session_id = Column(String, nullable=True)
    is_attack = Column(Boolean, default=False)
```

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

engine = create_engine(os.environ["DATABASE_URL"])
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)
```

### A5. Migration Points
- **Write:** every place currently appending to the JSON log after a guardrail check or order action → `session.add(AuditLog(...)); session.commit()`
- **Read:** `GET /api/audit-logs` reading the JSON file → query Postgres, serialize to the *same response shape* the frontend already expects — zero frontend changes needed.
- Do not touch: guardrail decision logic, spend cap checks, catalog.

### A6. Verification Checklist
- [ ] `create_order` writes a row, visible in Neon's SQL console
- [ ] `GET /api/audit-logs` returns identical JSON shape as before
- [ ] A blocked action (spend-cap violation) logs correctly with `result = "blocked"`
- [ ] `.env` with real connection string is not committed
- [ ] Re-run all 3 existing red-team attacks post-migration — confirm identical logging/blocking behavior

### A7. Pitch line to add
*"Audit logs are persisted in a managed Postgres database, queryable in real time — not a flat file that could be edited after the fact."*

---

## Part B — Catalog Images (~45 min - 1 hr)

### B1. Storage structure — static files, no upload feature, no DB storage for images
```
backend/
  static/
    images/
      SH001.jpg
      SH002.jpg
      ...
  data/
    catalog.json
```

### B2. Updated catalog.json shape (adds `category` + `image`)
```json
[
  {
    "sku": "SH001",
    "name": "Running Shoes - Blue",
    "category": "footwear",
    "price": 2499,
    "stock": 12,
    "tags": ["shoes", "running"],
    "image": "/static/images/SH001.jpg"
  }
]
```

### B3. Steps
1. Source 15-20 images from Unsplash or Pexels (free, no attribution required) — avoid pulling from real retailer product pages.
2. Batch-resize all to a consistent square size (~400-800px) using any free bulk resizer or a quick PIL script.
3. Rename each file to match its SKU exactly (`SH001.jpg`) — lets the frontend build the path directly from SKU, no lookup logic needed.
4. Drop into `backend/static/images/`.
5. Add `"image"` field to every catalog entry.
6. Serve the static folder — FastAPI: `app.mount("/static", StaticFiles(directory="static"), name="static")`.
7. Render in product card component: `<img src={product.image} />`.

### B4. Verification Checklist
- [ ] All SKUs have a matching image file, correctly named
- [ ] `/static/images/SH001.jpg` loads directly in browser (confirms mount is working)
- [ ] Product cards in chat UI render images correctly, consistent sizing
- [ ] No broken image icons after a fresh page load

---

## Deferred to Tomorrow (do not start today)
- Tier 1: 4th red-team attack (multi-turn/subtle), quantified metrics panel, documented near-miss story
- Tier 2: live deployment (Render/Railway + Vercel), latency display

## End-of-Day Success Criteria
- [ ] Audit log fully running on Neon, JSON file no longer used
- [ ] Catalog has images for every product, rendering correctly in UI
- [ ] All 3 existing red-team attacks still pass after migration
- [ ] Nothing else touched — agent logic, guardrail engine, and Razorpay integration unchanged from yesterday
