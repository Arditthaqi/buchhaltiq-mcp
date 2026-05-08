# Workflow 04 — Customer overview

## Scenario

A founder is about to call one of her customers and wants a 30-second briefing: who they are, what they've ordered, what's outstanding, what their payment behavior has looked like. She doesn't have time to click through three different views in BuchhaltIQ.

This workflow is the most common multi-tool example: Claude has to combine **two** tool calls into a single coherent answer.

## The prompt

> Gib mir einen Überblick über den Kunden cust_002 — wer das ist, was bei ihm offen ist, wie sein Zahlverhalten aussieht.

## Under the hood

Claude calls two tools in sequence and stitches the result:

```
get_customer(customer_id="cust_002")
# → {"id": "cust_002", "name": "Café Donaublick (Demo)",
#    "contact_email": "buchhaltung@donaublick-demo.example",
#    "city": "Regensburg", "country": "DE"}

list_invoices(customer_id="cust_002")
# → [
#     {"id": "inv_2026_0008", "issue_date": "2026-04-25",
#      "status": "draft",   "total_gross": "1404.20", ...},
#     {"id": "inv_2026_0003", "issue_date": "2026-02-03",
#      "status": "overdue", "total_gross": "1475.60", ...},
#   ]
```

The order of calls matters: Claude resolves the human-readable name *first*, so the response can lead with "Café Donaublick" instead of the raw ID.

## Sample response

> **Café Donaublick (Demo)** — `cust_002`, sitzt in Regensburg.
> Kontakt: `buchhaltung@donaublick-demo.example`.
>
> **Aktuelle Vorgänge (2 Rechnungen):**
>
> | Rechnung | Datum | Status | Betrag |
> |---|---|---|---:|
> | inv_2026_0003 — Beratungsleistung Q1 | 03.02.2026 | **überfällig** (seit 05.03.) | 1.475,60 € |
> | inv_2026_0008 — Beratungsleistung Q2 | 25.04.2026 | Entwurf | 1.404,20 € |
>
> **Beobachtungen für dein Telefonat:**
>
> - Eine Q1-Rechnung ist seit über zwei Monaten überfällig — das wäre der erste Punkt im Gespräch.
> - Die Q2-Rechnung ist noch im Entwurf, also formal noch nicht offen. Du könntest fragen, ob bei der Q2-Beratung schon etwas geliefert wurde, das du jetzt fertig in Rechnung stellen kannst.
> - Beide Rechnungen sind im selben Größenbereich (~1.400 €), also wirkt das nicht wie ein einmaliger Ausreißer, sondern wie ein wiederkehrendes Beratungs-Mandat.
>
> Soll ich dir Stichpunkte für das Gespräch formulieren?

## Why this matters

The "customer overview" lives at the intersection of three or four BuchhaltIQ views (customer master data, invoice list, dunning history, communication log). Compiling a briefing by hand takes 2–3 minutes per customer; Claude does it in five seconds and adds light interpretation ("eine Q1-Rechnung ist seit über zwei Monaten überfällig") that a raw view doesn't volunteer.

Crucially, Claude doesn't *invent* facts — every claim in the response traces back to a tool call. The "two months overdue" comes from a date subtraction on real fields, not from a hunch. That's the difference between an LLM with tools and an LLM without.

## Variations to try

- "und wie viel hat er insgesamt schon bezahlt?" — Claude calls `list_invoices(customer_id="cust_002", status="paid")` and sums.
- "vergleich ihn mit cust_001" — Claude runs the same two-call pattern on the second customer and produces a side-by-side.
- "schreib mir eine E-Mail an cust_002, die freundlich, aber bestimmt nach der überfälligen Q1-Rechnung fragt" — pure composition, no further tool calls; Claude already has the contact e-mail and the invoice details.
