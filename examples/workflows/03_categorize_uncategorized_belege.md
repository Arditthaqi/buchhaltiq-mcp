# Workflow 03 — Categorize a batch of new receipts

## Scenario

A bakery owner just exported a CSV of last week's card transactions from her bank. None of them have accounting categories yet. She doesn't want to fill out 30 dropdowns by hand — she wants Claude to suggest a category for each, with a reason, so she can confirm and post them.

## The prompt

> Hier sind drei neue Belege, die ich gerade aus der Bank exportiert habe. Bitte ordne mir jeden einer Buchhaltungs-Kategorie zu und sag mir kurz, warum.
>
> 1. Shell Tankstelle, 92,40 €, "Diesel Lieferfahrzeug Sprinter 23.04."
> 2. Vodafone GmbH, 49,90 €, "Mobilfunk-Vertrag Geschäftshandy April"
> 3. Kaufland, 187,55 €, "Wochenmarkt Mehl, Hefe, Zucker, Eier"

## Under the hood

Claude calls `categorize_transaction` once per transaction:

```
categorize_transaction(
    vendor="Shell Tankstelle",
    description="Diesel Lieferfahrzeug Sprinter 23.04.",
    amount_gross="92.40",
)
# → category: "Fahrzeugkosten",
#   matched_rule: "Vendor or description matches fuel, Tankstelle, or motoring service.",
#   confidence: "rule_based"

categorize_transaction(
    vendor="Vodafone GmbH",
    description="Mobilfunk-Vertrag Geschäftshandy April",
    amount_gross="49.90",
)
# → category: "Telekommunikation",
#   matched_rule: "Vendor or description matches a telecommunications provider or service.",
#   confidence: "rule_based"

categorize_transaction(
    vendor="Kaufland",
    description="Wochenmarkt Mehl, Hefe, Zucker, Eier",
    amount_gross="187.55",
)
# → category: "Wareneinkauf",
#   matched_rule: "Vendor or description matches a wholesale / grocery supplier.",
#   confidence: "rule_based"
```

## Sample response

> Habe ich kategorisiert — alle drei mit hoher Sicherheit (regelbasierter Treffer):
>
> | # | Lieferant | Betrag | Vorschlag | Begründung |
> |---|---|---:|---|---|
> | 1 | Shell Tankstelle | 92,40 € | **Fahrzeugkosten** | Lieferant + Beschreibung deuten auf Kraftstoff / Tankstelle. |
> | 2 | Vodafone GmbH | 49,90 € | **Telekommunikation** | Vodafone ist als Telko-Anbieter erkannt; "Mobilfunk" bestätigt es. |
> | 3 | Kaufland | 187,55 € | **Wareneinkauf** | Kaufland ist als Großhändler / Lebensmittelhändler hinterlegt; passt zur Liste der Zutaten. |
>
> Soll ich die Buchungen in BuchhaltIQ direkt anlegen, oder möchtest du sie vorher noch durchgehen?

## Why this matters

Categorization is the single most repetitive task in small-business bookkeeping. Most operators do it weekly, on a couch, half-attentive — which is exactly the case where mistakes (wrong account, lost VAT) compound silently. A rule-based first pass catches the obvious 70–80 %; the operator can then focus their attention on the ambiguous 20 %.

The audit trail (`matched_rule` per transaction) is critical: a tax advisor reviewing the books later can see *why* each category was chosen, not just that it was. Compare this to a black-box ML categorizer — the audit trail is the difference between "the model decided" and "this rule decided, here's the rule".

## Variations to try

- "und wenn der Vorschlag falsch ist?" — Claude offers to override and re-run with a manual category, and (in production mode) writes the override back to BuchhaltIQ for next time.
- "kategorisiere alle Belege im April, die noch keine Kategorie haben" — once the production-mode wiring lands, this triggers a batch loop over `list_belege(category=None, …)` followed by a per-row `categorize_transaction`.
- "warum hast du Bäckerei-Wareneinkauf bei Kaufland gewählt und nicht bei METRO?" — the rationale string lets Claude explain its own decision without making one up.
