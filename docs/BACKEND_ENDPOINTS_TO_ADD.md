# Backend Endpoints To Add

This is a copy-paste-ready FastAPI specification for the four read endpoints the MCP server expects to find on the BuchhaltIQ backend. Add them once, restart the backend, and the four currently-stubbed MCP tools (`list_invoices`, `get_customer`, `search_belege`, `monthly_report`) become live.

> **Rationale for putting this in the MCP repo, not the backend repo:** the cross-repo edit is intentionally scoped out — the MCP repo owns its expectations of the backend, and the backend repo owns the implementation. This file is the contract.

## Where it goes

Open `app/modules/user_invoices/routes.py` in the BuchhaltIQ backend. Add the block below at the **top of the route definitions** (right after the `router = APIRouter(...)` line), so the new GET endpoints sit visually together. The existing POST/PUT/DELETE routes stay below.

The endpoints reuse the existing `Depends(get_current_user)` auth pattern — they are uid-scoped via the Firebase ID token in `Authorization: Bearer …`.

## Imports to add at the top of the file

```python
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException, Query

from app.core.firebase_init import get_firestore_client
from app.core.services.category_manager import category_manager
```

(`datetime`, `Optional`, etc. may already be imported; deduplicate.)

## The four endpoints (paste into `routes.py`)

```python
# ============================================================================
# READ ENDPOINTS — for MCP-server integration (buchhaltiq-mcp)
# ============================================================================
# These complement the existing POST/PUT/DELETE routes by exposing list /
# detail / aggregate views the MCP tools need. Each endpoint is uid-scoped
# via Depends(get_current_user) — no admin / cross-tenant access.
#
# Filters are applied in-memory after a per-user Firestore fetch (no
# composite indexes required). Acceptable while invoice volume per user
# stays small; revisit when a single user crosses ~1k invoices.
# ============================================================================


_UNCATEGORIZED_VALUES = {
    "",
    "nicht kategorisiert",
    "uncategorized",
    "unkategorisiert",
    "unknown",
}


def _coerce_date(raw):
    """Best-effort conversion of Firestore date / datetime / ISO-string to date."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _coerce_money(raw):
    """Render a Firestore money field as a 2-decimal string (Decimal-friendly)."""
    if raw is None:
        return None
    try:
        return f"{Decimal(str(raw)):.2f}"
    except Exception:
        return None


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _posting_class_value(raw):
    if raw is None:
        return None
    if hasattr(raw, "value"):
        raw = raw.value
    value = str(raw).strip().lower()
    return value or None


def _meaningful_category(raw):
    if raw is None:
        return None
    value = str(raw).strip()
    if value.lower() in _UNCATEGORIZED_VALUES:
        return None
    return value


def _transaction_posting_class(data: dict):
    direct = _posting_class_value(_first_present(data.get("posting_class"), data.get("postingClass")))
    if direct:
        return direct

    category = _meaningful_category(
        _first_present(data.get("categoryId"), data.get("category_id"), data.get("category"))
    )
    if not category:
        return None

    return _posting_class_value(category_manager.get_posting_class(category))


def _is_pnl_transaction(data: dict) -> bool:
    return _transaction_posting_class(data) == "pnl"


def _project_invoice(doc_id: str, data: dict) -> dict:
    """Project a Firestore invoice document into the MCP-friendly shape."""
    issue_date = (
        data.get("date")
        or data.get("invoice_date")
        or data.get("invoiceDate")
        or data.get("createdAt")
        or data.get("created_at")
    )
    due_date = data.get("dueDate") or data.get("due_date")
    customer = data.get("customer") or {}
    totals = data.get("totals") or {}
    issued = _coerce_date(issue_date)
    due = _coerce_date(due_date)
    return {
        "id": doc_id,
        "invoice_number": data.get("invoiceNumber") or data.get("invoice_number") or "",
        "customer_id": data.get("customerId") or data.get("customer_id") or "",
        "customer_name": customer.get("name") or customer.get("companyName"),
        "issue_date": issued.isoformat() if issued else None,
        "due_date": due.isoformat() if due else None,
        "status": data.get("status") or "",
        "total_net": _coerce_money(totals.get("netAmount") or data.get("totalNet")),
        "total_gross": _coerce_money(totals.get("grossAmount") or data.get("totalGross")),
        "currency": data.get("currency") or "EUR",
        "description": data.get("notes") or "",
    }


@router.get("/list", summary="List the authenticated user's invoices for MCP")
async def list_user_invoices(
    status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    customer_id: Optional[str] = Query(None, description="Filter by customer id"),
    issued_from: Optional[date] = Query(None, description="Inclusive ISO date lower bound"),
    issued_to: Optional[date] = Query(None, description="Inclusive ISO date upper bound"),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """List the authenticated user's own invoices, newest first.

    Backs the MCP `list_invoices` tool. Filters are applied in-memory.
    """
    db = get_firestore_client()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    uid = current_user["uid"]
    invoices_ref = db.collection("users").document(uid).collection("invoices")

    rows: List[dict] = []
    for snapshot in invoices_ref.stream():
        data = snapshot.to_dict() or {}
        projected = _project_invoice(snapshot.id, data)
        if status and projected["status"] != status:
            continue
        if customer_id and projected["customer_id"] != customer_id:
            continue
        if issued_from and (
            projected["issue_date"] is None or projected["issue_date"] < issued_from.isoformat()
        ):
            continue
        if issued_to and (
            projected["issue_date"] is None or projected["issue_date"] > issued_to.isoformat()
        ):
            continue
        rows.append(projected)

    rows.sort(key=lambda r: r["issue_date"] or "", reverse=True)
    return {"items": rows[:limit], "count": len(rows[:limit])}


@router.get("/customers", summary="Aggregate the user's customers from invoice snapshots")
async def list_user_customers(current_user: dict = Depends(get_current_user)):
    """Return one entry per unique customerId, derived from invoice snapshots.

    Customers are not stored in a dedicated Firestore subcollection in this
    architecture — each invoice carries a denormalised ``customer`` snapshot.
    This endpoint deduplicates by customerId, keeping the most recent
    snapshot's data. Backs the MCP `get_customer` tool when called with
    a specific id (the MCP filters client-side).
    """
    db = get_firestore_client()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    uid = current_user["uid"]
    invoices_ref = db.collection("users").document(uid).collection("invoices")

    by_id: dict = {}
    by_id_dates: dict = {}
    for snapshot in invoices_ref.stream():
        data = snapshot.to_dict() or {}
        cid = data.get("customerId") or data.get("customer_id") or ""
        if not cid:
            continue
        customer = data.get("customer") or {}
        issued = _coerce_date(
            data.get("date") or data.get("invoiceDate") or data.get("invoice_date")
        )
        issued_iso = issued.isoformat() if issued else ""
        if cid in by_id_dates and by_id_dates[cid] >= issued_iso:
            continue
        by_id_dates[cid] = issued_iso
        by_id[cid] = {
            "id": cid,
            "name": customer.get("name") or customer.get("companyName") or "",
            "company_name": customer.get("companyName"),
            "contact_email": customer.get("email"),
            "city": customer.get("city"),
            "country": customer.get("country") or "DE",
            "vat_id": customer.get("vatId"),
            "tax_number": customer.get("taxNumber"),
        }
    return {"items": list(by_id.values()), "count": len(by_id)}


@router.get("/transactions", summary="Search the user's bank transactions as Belege")
async def search_user_transactions(
    q: Optional[str] = Query(None, description="Substring against vendor / purpose"),
    issued_from: Optional[date] = Query(None),
    issued_to: Optional[date] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Substring-search the user's bank transactions, newest first.

    Backs the MCP `search_belege` tool. Each transaction is projected
    into a Beleg-shaped dict (vendor / description / amount_gross /
    issue_date / category if present).
    """
    db = get_firestore_client()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    uid = current_user["uid"]
    tx_ref = db.collection("users").document(uid).collection("transactions")

    needle = (q or "").strip().lower()
    rows: List[dict] = []
    for snapshot in tx_ref.stream():
        data = snapshot.to_dict() or {}
        booking_date = _coerce_date(
            data.get("bookingDate") or data.get("booking_date") or data.get("valueDate")
        )
        if booking_date is None:
            continue
        if issued_from and booking_date < issued_from:
            continue
        if issued_to and booking_date > issued_to:
            continue
        vendor = (
            data.get("counterpartName")
            or data.get("creditorName")
            or data.get("debtorName")
            or data.get("vendor")
            or ""
        )
        purpose = data.get("purpose") or data.get("description") or ""
        if needle and needle not in f"{vendor} {purpose}".lower():
            continue
        rows.append(
            {
                "id": snapshot.id,
                "issue_date": booking_date.isoformat(),
                "vendor": vendor,
                "amount_gross": _coerce_money(data.get("amount") or data.get("amountGross")),
                "category": data.get("category") or data.get("categoryId"),
                "description": purpose,
            }
        )

    rows.sort(key=lambda r: r["issue_date"], reverse=True)
    return {"items": rows[:limit], "count": len(rows[:limit])}


@router.get("/monthly-report", summary="BWA-style monthly aggregate for MCP")
async def monthly_report_for_user(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: dict = Depends(get_current_user),
):
    """Aggregate revenue and P&L-relevant bank transaction expenses for the month."""
    db = get_firestore_client()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    uid = current_user["uid"]
    revenue = Decimal("0.00")
    expense = Decimal("0.00")
    expense_excluded = Decimal("0.00")
    invoice_count = 0
    beleg_count = 0
    excluded_beleg_count = 0

    revenue_statuses = {"paid", "open", "overdue", "sent"}
    invoices_ref = db.collection("users").document(uid).collection("invoices")
    for snapshot in invoices_ref.stream():
        data = snapshot.to_dict() or {}
        issued = _coerce_date(
            data.get("date") or data.get("invoiceDate") or data.get("invoice_date")
        )
        if issued is None or issued.year != year or issued.month != month:
            continue
        status = data.get("status") or ""
        if status not in revenue_statuses:
            continue
        totals = data.get("totals") or {}
        gross_str = _coerce_money(totals.get("grossAmount") or data.get("totalGross")) or "0.00"
        revenue += Decimal(gross_str)
        invoice_count += 1

    tx_ref = db.collection("users").document(uid).collection("transactions")
    for snapshot in tx_ref.stream():
        data = snapshot.to_dict() or {}
        booking_date = _coerce_date(
            data.get("bookingDate") or data.get("booking_date") or data.get("valueDate")
        )
        if booking_date is None or booking_date.year != year or booking_date.month != month:
            continue
        amount_str = _coerce_money(data.get("amount") or data.get("amountGross"))
        if amount_str is None:
            continue
        amount = Decimal(amount_str)
        if amount < 0:
            outflow = -amount
            if _is_pnl_transaction(data):
                expense += outflow
                beleg_count += 1
            else:
                expense_excluded += outflow
                excluded_beleg_count += 1

    return {
        "year": year,
        "month": month,
        "revenue_total": f"{revenue:.2f}",
        "expense_total": f"{expense:.2f}",
        "profit": f"{revenue - expense:.2f}",
        "currency": "EUR",
        "invoice_count": invoice_count,
        "beleg_count": beleg_count,
        "expense_excluded_total": f"{expense_excluded:.2f}",
        "expense_excluded_count": excluded_beleg_count,
        "expense_filter": "Only negative bank transactions with posting_class=pnl are counted.",
    }
```

## Smoke test after pasting

Restart the backend (`uvicorn app.main:app --reload --port 8080`). Then with a valid Firebase ID token in your shell:

```bash
TOKEN="<your-firebase-id-token>"

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/user-invoices/list?limit=5" | jq

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/user-invoices/customers" | jq

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/user-invoices/transactions?q=METRO&limit=10" | jq

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/user-invoices/monthly-report?year=2026&month=3" | jq
```

If your data uses field names that diverge from the heuristics in `_coerce_date` / `_coerce_money` / `_project_invoice` (e.g. `invoiceDate` instead of `date`), the helpers fall through several aliases — but if a field is named something completely unexpected, the projection will return `None` for that field and the MCP tool will surface a partial result.

## Field-name fallbacks the helpers handle

| Concept | Names checked, in order |
|---|---|
| Invoice issue date | `date` → `invoice_date` → `invoiceDate` → `createdAt` → `created_at` |
| Invoice due date | `dueDate` → `due_date` |
| Invoice gross | `totals.grossAmount` → `totalGross` |
| Invoice net | `totals.netAmount` → `totalNet` |
| Transaction booking date | `bookingDate` → `booking_date` → `valueDate` |
| Transaction vendor | `counterpartName` → `creditorName` → `debtorName` → `vendor` |
| Transaction purpose | `purpose` → `description` |
| Transaction amount | `amount` → `amountGross` |

If any of these are wrong for your data, edit the helper functions — they are isolated and easy to fix.
