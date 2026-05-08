# Workflow 01 — Overdue invoices for Q1

## Scenario

A small-business owner wants to know which invoices are overdue from the first quarter, so she can prioritize her dunning calls. She does not want to log into BuchhaltIQ, click through the invoice list, sort by status, and filter by date — she wants the answer in one sentence.

## The prompt

> Zeig mir alle überfälligen Rechnungen aus dem ersten Quartal 2026.

## Under the hood

Claude inspects the available tools and decides a single call is enough:

```
list_invoices(
    status="overdue",
    issued_from="2026-01-01",
    issued_to="2026-03-31",
)
```

Against the demo fixtures this returns one row:

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

## Sample response

> Im ersten Quartal 2026 gibt es **eine überfällige Rechnung**:
>
> - **inv_2026_0003** — Beratungsleistung Q1 für `cust_002`
>   - Ausgestellt am 03.02.2026, fällig zum 05.03.2026 (mittlerweile über zwei Monate überfällig).
>   - Brutto: **1.475,60 €** (Netto 1.240,00 €).
>
> Soll ich dir den Text für eine freundliche Mahnung formulieren? Wenn ja, sag mir, ob mit oder ohne Mahngebühr.

## Why this matters

The user typed one sentence in German and got back a single, decision-ready bullet. The alternative — opening the app, navigating to invoices, sorting by status, filtering by date — is around eight clicks and reaches the same answer. The win compounds when the same user has 200 invoices instead of eight: the LLM scales, the UI does not.

## Variations to try

- "und für Q2?" — Claude reuses the conversational context and re-issues the call with `issued_from="2026-04-01"` / `issued_to="2026-06-30"`.
- "wer schuldet mir am meisten?" — Claude calls `list_invoices` without the `overdue` filter, sums per `customer_id`, and resolves the top result via `get_customer`.
- "schreib eine Mahnung an cust_002" — purely composition, no further tool calls; Claude already has the data.
