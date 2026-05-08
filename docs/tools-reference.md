# Tools Reference

Authoritative reference for every tool the MCP server exposes. For conversational examples in context, see [`../examples/workflows/`](../examples/workflows/). For the design rationale behind these tools, see [`architecture.md`](architecture.md).

All tools share two cross-cutting behaviors:

- **Modes.** Each tool ships with a complete demo-mode implementation and a production-mode stub that raises `ProductionNotImplementedError`. The demo path reads from the fixtures under [`../data/`](../data/); the production path will read from `api.buchhaltiq.de` once Phase 2 wiring lands.
- **Money.** Every monetary value is a `Decimal` internally and a decimal-string in the JSON response (e.g. `"1475.60"`, never `1475.6` as a JSON number). This preserves precision through the LLM round-trip.

---

## `list_invoices`

List invoices with optional status, customer, and date-range filters. Newest first by issue date.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `status` | `"draft" \| "open" \| "paid" \| "overdue" \| "cancelled" \| null` | `null` | Restrict to invoices in this lifecycle state. |
| `customer_id` | `string \| null` | `null` | Restrict to invoices for a single customer (e.g. `"cust_002"`). |
| `issued_from` | `date \| null` | `null` | Inclusive lower bound on `issue_date` (ISO 8601, e.g. `"2026-01-01"`). |
| `issued_to` | `date \| null` | `null` | Inclusive upper bound on `issue_date`. |
| `limit` | `integer` | `50` | Maximum rows to return. Clamped to `[1, 200]`. |

### Returns

A list of invoice objects:

```json
[
  {
    "id": "inv_2026_0003",
    "customer_id": "cust_002",
    "issue_date": "2026-02-03",
    "due_date": "2026-03-05",
    "status": "overdue",
    "total_net": "1240.00",
    "total_gross": "1475.60",
    "currency": "EUR",
    "description": "Beratungsleistung Q1"
  }
]
```

### Errors

- `ProductionNotImplementedError` — when `BUCHHALTIQ_MCP_MODE=production`.
- Invalid `status` strings or malformed dates are rejected at the MCP-schema level before the tool body runs.

### Natural-language example

> "Zeig mir alle überfälligen Rechnungen aus Q1 2026."

becomes

```python
list_invoices(status="overdue", issued_from="2026-01-01", issued_to="2026-03-31")
```

---

## `get_customer`

Fetch a single customer by ID.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `customer_id` | `string` | required | Stable identifier (e.g. `"cust_001"`). Must be non-empty after stripping whitespace. |

### Returns

```json
{
  "id": "cust_001",
  "name": "Restaurant Schinderhannes (Demo)",
  "contact_email": "kontakt@schinderhannes-demo.example",
  "city": "Mainz",
  "country": "DE"
}
```

### Errors

- `ValueError` — `customer_id` is empty or whitespace.
- `NotFoundError` — no customer with that ID exists.
- `ProductionNotImplementedError` — production mode.

### Natural-language example

> "Wer ist eigentlich cust_002?"

becomes

```python
get_customer(customer_id="cust_002")
```

---

## `search_belege`

Full-text search over receipts (`Belege`). Substring match against `vendor` and `description`, case-insensitive, newest first.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | required | Search term. Must be non-empty after stripping. Matched as a substring against `vendor + " " + description`, case-insensitively. |
| `limit` | `integer` | `20` | Maximum rows. Clamped to `[1, 100]`. |

### Returns

```json
[
  {
    "id": "bel_001",
    "issue_date": "2026-01-12",
    "vendor": "METRO Cash & Carry",
    "amount_gross": "238.45",
    "category": "Wareneinkauf",
    "description": "Großhandel: Mehl, Hefe, Tomatensauce, Pizzakäse für Pizzeria-Catering"
  }
]
```

### Errors

- `ValueError` — `query` is empty or whitespace.
- `ProductionNotImplementedError` — production mode.

### Natural-language example

> "Such mir alle Belege, in denen Diesel vorkam."

becomes

```python
search_belege(query="Diesel")
```

---

## `monthly_report`

BWA-style monthly profit-and-loss summary. Revenue is the sum of gross totals of invoices issued in the month with status `paid`, `open`, or `overdue` — drafts and cancellations are excluded. Expenses are the sum of gross amounts of receipts dated in the month. Profit is revenue minus expenses, all in two-decimal precision.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `year` | `integer` | required | Four-digit calendar year. Must be in `[2000, 2100]`. |
| `month` | `integer` | required | Month number, `[1, 12]`. |

### Returns

```json
{
  "year": 2026,
  "month": 3,
  "revenue_total": "4319.70",
  "expense_total": "207.79",
  "profit": "4111.91",
  "currency": "EUR",
  "invoice_count": 2,
  "beleg_count": 2
}
```

### Errors

- `ValueError` — `year` outside `[2000, 2100]` or `month` outside `[1, 12]`.
- `ProductionNotImplementedError` — production mode.

### Natural-language example

> "Wie lief der März?"

becomes

```python
monthly_report(year=2026, month=3)
```

---

## `categorize_transaction`

Map a transaction (vendor + description) to a German accounting category. Rule-based with an explicit rationale for every match — no black-box ML.

The current rule set covers seven categories: `Wareneinkauf`, `Telekommunikation`, `Fahrzeugkosten`, `Porto`, `Geringwertige Wirtschaftsgüter`, `Buchhaltungssoftware`, `Reisekosten`. Inputs that match no rule fall through to `Unkategorisiert` with `confidence: "fallback"`, never silently misclassified.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `description` | `string` | required | Free-text description (e.g. `"Diesel Sprinter Lieferfahrzeug"`). May be empty if `vendor` is provided. |
| `amount_gross` | `string` | required | Gross amount as a decimal string (e.g. `"238.45"`). Validated as `Decimal`; currently echoed back. Reserved for amount-aware rules in a future revision. |
| `vendor` | `string \| null` | `null` | Optional vendor name. If provided, takes priority during matching (rules see `vendor + " " + description`). |

### Returns

```json
{
  "category": "Wareneinkauf",
  "matched_rule": "Vendor or description matches a wholesale / grocery supplier.",
  "confidence": "rule_based",
  "vendor": "METRO Cash & Carry",
  "description": "Großhandel: Mehl, Hefe",
  "amount_gross": "238.45"
}
```

`confidence` is one of:

- `"rule_based"` — a curated rule fired; `matched_rule` describes which.
- `"fallback"` — no rule matched; `matched_rule` is the fallback message and `category` is `"Unkategorisiert"`.

### Errors

- `ValueError` — both `description` and `vendor` are empty / whitespace.
- `ValueError` — `amount_gross` is not parseable as a `Decimal`.
- `ProductionNotImplementedError` — production mode.

### Natural-language example

> "Wie würdest du diesen Beleg buchen: METRO Cash & Carry, 238,45 €, Großhandel-Einkauf?"

becomes

```python
categorize_transaction(
    vendor="METRO Cash & Carry",
    description="Großhandel-Einkauf",
    amount_gross="238.45",
)
```

---

## Summary table

| Tool | Reads | Returns | Notable validation |
|---|---|---|---|
| `list_invoices` | invoices fixture | list of invoices, newest first | none beyond schema; limit clamped to `[1, 200]` |
| `get_customer` | customers fixture | one customer | non-empty ID; raises `NotFoundError` on miss |
| `search_belege` | belege fixture | list of belege | non-empty query; limit clamped to `[1, 100]` |
| `monthly_report` | invoices + belege | aggregated totals | `year ∈ [2000, 2100]`, `month ∈ [1, 12]` |
| `categorize_transaction` | rule table (in code) | category + rationale + echo | at least one of vendor/description; `amount_gross` parseable |

Each tool has a corresponding test file under [`../tests/`](../tests/) covering happy path, validation errors, and the production stub. Adding a sixth tool follows the seven-step pattern documented in [`architecture.md`](architecture.md#adding-a-new-tool--the-seven-step-pattern).
