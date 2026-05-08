# Workflow 02 — Monthly summary

## Scenario

A founder is on a Monday-morning standup with her co-founder and wants a quick read on how March looked: revenue, expenses, profit, and anything noteworthy. She doesn't want to wait for the BWA from her tax advisor — she wants a sanity check now.

## The prompt

> Wie lief der März? Gib mir eine kurze Zusammenfassung.

## Under the hood

Claude routes this to a single aggregation call:

```
monthly_report(year=2026, month=3)
```

Against the demo fixtures this returns:

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

The rule the tool applies: revenue counts invoices whose status is `paid`, `open`, or `overdue` and whose issue date falls in the month — drafts are excluded because they are not yet billed, cancellations because they will never become revenue.

## Sample response

> **März 2026 auf einen Blick**
>
> | | EUR |
> |---|---:|
> | Erlöse (2 Rechnungen) | 4.319,70 |
> | Aufwendungen (2 Belege) | 207,79 |
> | **Gewinn** | **4.111,91** |
>
> Die zwei Rechnungen sind beide noch offen — also kein Cash, sondern Forderungen. Auf der Aufwandsseite steht nur Telekom (59,99 €) und ein OBI-Einkauf (147,80 €). Im Vergleich zum Februar war das ein deutlich umsatzstärkerer Monat, allerdings ist der Großteil noch nicht bezahlt.
>
> Willst du, dass ich dir den Cash-Stand schätze (also nur bezahlte Rechnungen), oder dir eine Übersicht der offenen Beträge gebe?

## Why this matters

A monthly snapshot is the single most-asked question in any small business — and the one that today usually requires either a DATEV export, a spreadsheet round-trip, or a wait for the next BWA. With one tool call and a sentence, the user gets a draft answer in seconds. They still need their tax advisor for the official numbers, but they can stop guessing about cash flow on Monday morning.

## Variations to try

- "vergleich März mit Februar" — Claude calls `monthly_report` twice and computes the delta.
- "und nur die bezahlten Beträge" — Claude calls `list_invoices(issued_from=…, issued_to=…, status="paid")` and re-aggregates.
- "wer war im März der größte Schuldner?" — Claude switches into customer-grouping logic, using `list_invoices` and `get_customer`.
