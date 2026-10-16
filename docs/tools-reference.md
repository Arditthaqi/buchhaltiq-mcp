# Tools Reference

Authoritative reference for every tool the MCP server exposes. For conversational examples in context, see [`../examples/workflows/`](../examples/workflows/). For the design rationale behind these tools, see [`architecture.md`](architecture.md).

All tools share two cross-cutting behaviors:

- **Modes.** Each tool has a deterministic demo-mode implementation. Tools whose BuchhaltIQ backend endpoint exists delegate to production in `BUCHHALTIQ_MCP_MODE=production`; pure helper tools still raise `ProductionNotImplementedError` until a live backend binding is added.
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

BWA-style monthly profit-and-loss summary, all in two-decimal precision.

- **Production mode:** the backend computes the numbers with the BuchhaltIQ accounting month overview — the same calculation as `accounting_month_overview`, the month report and the app (one result, by cash flow). Revenue is POS revenue from daily reports plus invoice payments of the month (credit-note payments subtracted, `origin=pos` excluded) plus standalone P&L income. Expenses are P&L expenses incl. wages; Umsatzsteuer (also prior years) and Gewerbesteuer count by cash flow, a refund reduces expenses; Einkommensteuer is private and never counts. Profit is revenue minus expenses.
- **Demo mode:** revenue is the sum of gross totals of fixture invoices issued in the month with status `paid`, `open`, or `overdue`; expenses are the gross amounts of fixture receipts dated in the month.

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

In **production mode** the response additionally carries where the
numbers come from and an audit trail of the filters:

```json
{
  "period_key": "2026-03",
  "pos_revenue": "3800.00",
  "standalone_income": "0.00",
  "invoice_gross_total": "519.70",
  "credit_note_gross_total": "0.00",
  "tax_payments_total": "150.00",
  "tax_payment_count": 1,
  "expense_excluded_total": "1200.00",
  "expense_excluded_count": 3,
  "inflow_on_expense_total": "0.00",
  "inflow_on_expense_count": 0,
  "result_rule": "euer-steuerzahlungen/2026-10-16",
  "revenue_filter": "...",
  "expense_filter": "...",
  "warnings": []
}
```

`invoice_count` and `credit_note_count` count payments of the month,
not invoice documents; `revenue_excluded_*` are always `0`. A closed
month can show a different result in the stored month report (old
rule); `result_rule` names the rule the numbers were computed with.
These fields are absent in demo mode.

### Errors

- `ValueError` — `year` outside `[2000, 2100]` or `month` outside `[1, 12]`.
- Production mode: the backend answers `409` when the month's source data
  cannot be reconciled (e.g. receipt positions that cannot explain the bank
  amount, unverified cashbook corrections or PosIQ cash movements) and `503`
  when Firestore is unavailable — the same as `accounting_month_overview`.

### Natural-language example

> "Wie lief der März?"

becomes

```python
monthly_report(year=2026, month=3)
```

---

## `accounting_month_overview`

BuchhaltIQ-aware accounting month overview. This is the richer successor to
`monthly_report` for product-aware questions: POS revenue comes from
`dailyReports.totalRevenue`, invoice revenue comes from actual payments by
`paidAt` and excludes `origin=pos`, standalone income is limited to exportable
P&L income categories, and expenses are grouped by P&L expense category.
Umsatzsteuer (also prior years) and Gewerbesteuer count by cash flow — a
payment is an expense, a refund reduces expenses — and are listed separately
in `expenses.tax_payments`; Einkommensteuer is private and never counts.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `period_key` | `string` | required | Month in `YYYY-MM` format, e.g. `2026-04`. |

### Returns

```json
{
  "period_key": "2026-04",
  "currency": "EUR",
  "income": {
    "total": "1288.00",
    "pos_revenue": "1000.00",
    "invoice_revenue": "188.00",
    "standalone_income": "100.00",
    "daily_report_count": 1,
    "invoice_payment_count": 2
  },
  "expenses": {
    "gross_expenses": "119.00",
    "refunds": "19.00",
    "net_expenses": "100.00",
    "by_category": [
      {
        "category_id": "wareneinkauf_material",
        "gross": "119.00",
        "refunds": "19.00",
        "net": "100.00"
      }
    ]
  },
  "profit": "1188.00",
  "readiness": {
    "missing_receipt_count": 1,
    "uncategorized_transaction_count": 0,
    "can_prepare_datev": false
  }
}
```

The response also includes `vat`, `source_counts`, `warnings`, and
`methodology` so Claude can explain where each number came from instead of
collapsing everything into a single total.

### Errors

- `ValueError` — `period_key` is not in `YYYY-MM` format.

### Natural-language example

> "Wie war mein April 2026 buchhalterisch?"

becomes

```python
accounting_month_overview(period_key="2026-04")
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

## `list_employees`

List BuchhaltIQ employees with optional status and employment-type filters.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `status` | `"active" \| "inactive" \| null` | `null` | Restrict by employee lifecycle status. |
| `employment_type` | `"minijob" \| "parttime" \| "fulltime" \| null` | `null` | Restrict by employment type. |
| `limit` | `integer` | `100` | Maximum rows. Clamped to `[1, 200]`. |
| `include_sensitive` | `boolean` | `false` | Include contact / DATEV-lock metadata only when explicitly requested. |

### Returns

```json
[
  {
    "id": "emp_001",
    "display_name": "Anna Mueller",
    "status": "active",
    "employment_type": "minijob",
    "hourly_rate": 15.0,
    "weekly_hours": 12.0,
    "datev_personnel_number": 101
  }
]
```

---

## `get_employee_work_summary`

Summarize one employee's work for a month. The tool explicitly separates
`shift_count` from `work_day_count`, so split shifts on the same day are
counted correctly.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `employee_id` | `string` | required | Employee document ID. |
| `period_key` | `string` | required | Month in `YYYY-MM` format. |
| `include_entries` | `boolean` | `false` | Include individual time-entry and absence rows. |

### Returns

```json
{
  "period_key": "2026-04",
  "employee": {"id": "emp_001", "display_name": "Anna Mueller"},
  "shift_count": 4,
  "work_day_count": 3,
  "gross_hours": 21.5,
  "break_hours": 1.25,
  "net_hours": 20.25,
  "calculated_wage": "303.75",
  "absence_days": 0.5,
  "absence_types": {"vacation": 0.5}
}
```

---

## `hr_month_overview`

Build the HR month overview Claude should use for questions like "Wie oft haben
meine Mitarbeiter im April gearbeitet?" or "Ist der Lohnmonat bereit?".

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `period_key` | `string` | required | Month in `YYYY-MM` format. |
| `include_entries` | `boolean` | `false` | Include raw entries/absences inside each employee summary. |

### Returns

```json
{
  "period_key": "2026-04",
  "status": "open",
  "can_edit": true,
  "active_employee_count": 2,
  "shift_count": 7,
  "work_day_count": 6,
  "total_net_hours": 40.25,
  "estimated_wage_total": "653.75",
  "absence_days": 2.5,
  "employee_summaries": []
}
```

### Errors

- `ValueError` — malformed `period_key` or invalid employee filter.
- `NotFoundError` — unknown employee in demo mode.

---

## `extract_vat_from_receipt`

Split a gross amount into net and VAT for a single tax rate. Decimal precision, ROUND_HALF_UP at two places — same convention as the backend's `calculate_amounts`.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `amount_gross` | `string` | required | Gross amount (decimal string, e.g. `"238.45"`). Non-negative. |
| `tax_rate` | `string` | required | VAT rate. Accepts percentage points (`"19"`) or fraction (`"0.19"`). Supported: 0, 7, 19. |

### Returns

```json
{
  "amount_gross": "238.45",
  "amount_net": "200.38",
  "tax_amount": "38.07",
  "tax_rate": "19",
  "currency": "EUR"
}
```

### Errors

- `ValueError` — amount not a decimal, amount negative, rate unsupported.
- `ProductionNotImplementedError` — production mode.

---

## `map_tax_rate_to_bu_key`

Look up the DATEV BU-key for a German VAT rate. Pure lookup against the same table the backend's `TaxKeyMapper` uses.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `tax_rate` | `string` | required | `"0"`, `"7"`, `"19"`, or fraction synonyms. |
| `is_expense` | `boolean` | `true` | `true` for purchase-side (Vorsteuer / Aufwand), `false` for sales-side (Umsatzsteuer / Erlös). |

### Returns

```json
{
  "bu_key": 9,
  "description": "19% Vorsteuer (Regelsatz, Aufwand)",
  "is_vorsteuer": true,
  "tax_rate": "19",
  "side": "expense"
}
```

### Errors

- `ValueError` — rate unsupported.

---

## `validate_datev_account`

Verify a DATEV account number against the SKR03 / SKR04 reference. Returns a structured result with title and type when valid, or near-match suggestions when invalid.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `skr` | `string` | required | `"SKR03"` or `"SKR04"`. Whitespace and case are normalised. |
| `account` | `string` | required | Account number as a string (preserves leading zeros). |

### Returns (valid)

```json
{
  "is_valid": true,
  "skr": "SKR03",
  "account": "4650",
  "title": "Bewirtungskosten (70% abziehbar)",
  "type": "Aufwand",
  "errors": [],
  "suggestions": []
}
```

### Returns (invalid)

```json
{
  "is_valid": false,
  "skr": "SKR03",
  "account": "1577",
  "errors": ["Account '1577' is not present in the SKR03 reference."],
  "suggestions": [
    {"skr": "SKR03", "account": "1576", "title": "Abziehbare Vorsteuer 19%", "type": "Steuerkonto"},
    {"skr": "SKR03", "account": "1571", "title": "Abziehbare Vorsteuer 7%", "type": "Steuerkonto"}
  ]
}
```

### Errors

- `ValueError` — `skr` not in `{SKR03, SKR04}`, or `account` empty.
- `ProductionNotImplementedError` — production mode.

---

## `apply_bewirtung_rule`

Apply the German Bewirtung deduction rule (§ 4 Abs. 5 Nr. 2 EStG): 70% of net is income-tax-deductible for client entertainment, 100% for in-house employee events. Input VAT is **fully recoverable in both cases** — the result names this explicitly to forestall a common categorisation error.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `amount_gross` | `string` | required | Gross amount (decimal string). Non-negative. |
| `tax_rate` | `string` | `"19"` | VAT rate. German Restaurantbewirtung is generally 19%. |
| `is_employee_event` | `boolean` | `false` | `true` for Mitarbeiterbewirtung (100% deductible), `false` for Geschäftsessen (70% deductible). |

### Returns

```json
{
  "amount_gross": "119.00",
  "amount_net": "100.00",
  "tax_amount": "19.00",
  "tax_rate": "19",
  "deductible_pct": 70,
  "net_deductible": "70.00",
  "net_non_deductible": "30.00",
  "vat_recoverable": "19.00",
  "rule": "Geschäftsessen 70%",
  "currency": "EUR"
}
```

### Errors

- `ValueError` — amount invalid or negative, rate unsupported.
- `ProductionNotImplementedError` — production mode.

---

## `split_mixed_tax_receipt`

Aggregate a list of positions into a per-rate VAT breakdown. The canonical "Edeka run" with food at 7%, household goods at 19%, and Pfand at 0% comes back as a clean three-bucket structure ready for posting.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `positions` | `list of objects` | required | Each entry: `{amount_gross, tax_rate, description?}`. Must have at least one item. |
| `expected_total_gross` | `string \| null` | `null` | Optional expected sum. If supplied and it differs from the computed sum, a non-empty `warnings` list is returned. |

### Returns

```json
{
  "positions": [
    {"description": "Lebensmittel", "amount_gross": "53.50", "amount_net": "50.00", "tax_amount": "3.50", "tax_rate": "7"},
    {"description": "Reiniger",     "amount_gross": "23.80", "amount_net": "20.00", "tax_amount": "3.80", "tax_rate": "19"}
  ],
  "total_gross": "77.30",
  "total_net": "70.00",
  "total_tax": "7.30",
  "has_mixed_tax": true,
  "breakdown_by_rate": {
    "7":  {"gross": "53.50", "net": "50.00", "tax": "3.50", "position_count": 1},
    "19": {"gross": "23.80", "net": "20.00", "tax": "3.80", "position_count": 1}
  },
  "warnings": [],
  "currency": "EUR"
}
```

### Errors

- `ValueError` — empty positions, negative position amount, unsupported rate.
- `ProductionNotImplementedError` — production mode.

---

## `resolve_account_assignment`

The full Kontierung wrapper — given a BuchhaltIQ category, returns a complete DATEV booking pair (account, contra-account, BU-key, debit/credit side, net/tax split). Mirrors `AccountResolutionService.resolve()` and the `POST /api/accounting/resolve` endpoint.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `category_id` | `string` | required | BuchhaltIQ category, e.g. `"wareneinkauf_material"`, `"bewirtung_geschaeftsessen"`, `"miete_pacht"`, `"erloese_19"`. |
| `amount_gross` | `string` | required | Gross amount (decimal string). Non-negative. |
| `payment_method` | `string` | `"bank"` | `"bank"` or `"cash"`. Selects the contra-account. Creditor postings are out of scope (require master-data). |
| `tax_rate` | `string \| null` | `null` | Explicit rate. Falls back to the category's default. **Tax-free categories override any non-zero input** to 0. |
| `skr` | `string` | `"SKR03"` | `"SKR03"` or `"SKR04"`. |

### Returns

```json
{
  "category_id": "wareneinkauf_material",
  "category_title": "Wareneinkauf Material",
  "side": "expense",
  "skr": "SKR03",
  "account": "3400",
  "account_title": "Wareneingang 19% Vorsteuer",
  "contra_account": "1200",
  "contra_account_title": "Bank",
  "debit_account": "3400",
  "credit_account": "1200",
  "bu_key": 9,
  "bu_key_description": "19% Vorsteuer (Regelsatz, Aufwand)",
  "tax_rate": "19",
  "amount_gross": "238.45",
  "amount_net": "200.38",
  "tax_amount": "38.07",
  "payment_method": "bank",
  "currency": "EUR",
  "validation": {
    "is_valid": true,
    "errors": []
  }
}
```

### Errors

- `ValueError` — invalid SKR, invalid payment method, malformed amount, unsupported rate.
- `NotFoundError` — unknown `category_id`.
- `ProductionNotImplementedError` — production mode.

---

## Summary table

| Tool | Reads | Returns | Notable validation |
|---|---|---|---|
| `list_invoices` | invoices fixture | list of invoices, newest first | none beyond schema; limit clamped to `[1, 200]` |
| `get_customer` | customers fixture | one customer | non-empty ID; raises `NotFoundError` on miss |
| `search_belege` | belege fixture | list of belege | non-empty query; limit clamped to `[1, 100]` |
| `monthly_report` | invoices + belege fixture / `/api/user-invoices/monthly-report` (month overview) | aggregated totals | `year ∈ [2000, 2100]`, `month ∈ [1, 12]` |
| `accounting_month_overview` | month_overviews fixture / `/api/mcp/month-overview/{period_key}` | BuchhaltIQ-aware month aggregate | `period_key` format |
| `list_employees` | hr_employees fixture / `/api/hr/employees` | employees, field-minimized | status/type validation; limit clamped to `[1, 200]` |
| `get_employee_work_summary` | HR employees + time entries + absences | one employee's monthly HR aggregate | `period_key` format; non-empty employee ID |
| `hr_month_overview` | HR employees + time entries + absences + month status | HR month aggregate | `period_key` format |
| `categorize_transaction` | rule table (in code) | category + rationale + echo | at least one of vendor/description; `amount_gross` parseable |
| `extract_vat_from_receipt` | _money.py logic only | net + tax + gross + rate | rate ∈ {0, 7, 19}; non-negative gross |
| `map_tax_rate_to_bu_key` | BU-key table (in code) | BU-key + description + side | rate ∈ {0, 7, 19} |
| `validate_datev_account` | datev_accounts fixture | structured validation + suggestions | `skr ∈ {SKR03, SKR04}`; non-empty account |
| `apply_bewirtung_rule` | _money.py logic only | 70/30 split + full Vorsteuer | rate ∈ {0, 7, 19}; non-negative gross |
| `split_mixed_tax_receipt` | _money.py logic only | per-rate breakdown + warnings | non-empty positions; per-position rate validation |
| `resolve_account_assignment` | categories + datev_accounts fixtures | full DATEV booking pair | unknown category → `NotFoundError`; tax-free override |

Each tool has a corresponding test file under [`../tests/`](../tests/) covering happy path, validation errors, and production behavior where wired. Adding another tool follows the seven-step pattern documented in [`architecture.md`](architecture.md#adding-a-new-tool--the-seven-step-pattern).
