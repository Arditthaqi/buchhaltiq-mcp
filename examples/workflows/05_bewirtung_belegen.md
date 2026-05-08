# Workflow 05 — Geschäftsessen mit korrekter Kontierung

## Scenario

A founder had dinner with a prospect, paid 238,45 € at the restaurant, and now wants to record the receipt correctly. "Correctly" means three things at once: the right SKR account, the 70 / 30 income-tax split per § 4 Abs. 5 Nr. 2 EStG, and the **full** Vorsteuer recovery (a regular source of mistakes — the 70 / 30 rule applies to the income-tax side only).

This is the workflow where the tax/Kontierung tools earn their keep: the user types one sentence, Claude orchestrates three tools, and produces a posting a Steuerberater can sign off on.

## The prompt

> Ich war gestern abend mit einem potenziellen Kunden essen, Restaurant-Beleg über 238,45 €. Wie buche ich das korrekt? Ich nutze SKR03, Zahlung lief über meine Geschäftskarte.

## Under the hood

Claude makes three tool calls in sequence, then composes the answer:

```
# 1. Apply the German 70/30 rule.
apply_bewirtung_rule(amount_gross="238.45", tax_rate="19")
# → amount_net=200.38, tax_amount=38.07,
#   net_deductible=140.27, net_non_deductible=60.11,
#   vat_recoverable=38.07, rule="Geschäftsessen 70%"

# 2. Resolve the SKR posting.
resolve_account_assignment(
    category_id="bewirtung_geschaeftsessen",
    amount_gross="238.45",
    payment_method="bank",
    skr="SKR03",
)
# → account=4650 (Bewirtungskosten), contra=1200 (Bank),
#   debit=4650, credit=1200, bu_key=9, ...

# 3. Sanity-check the booking account exists.
validate_datev_account(skr="SKR03", account="4650")
# → is_valid=true, title="Bewirtungskosten (70% abziehbar)"
```

## Sample response

> **Buchung für deinen Bewirtungsbeleg vom 7. Mai 2026 — 238,45 € brutto**
>
> | | EUR |
> |---|---:|
> | Brutto | 238,45 |
> | Netto (19% USt herausgerechnet) | 200,38 |
> | Vorsteuer (voll abziehbar) | 38,07 |
>
> **Einkommensteuerlicher Abzug nach § 4 Abs. 5 Nr. 2 EStG:**
>
> - 70% des Netto = **140,27 €** sind abziehbar.
> - 30% des Netto = **60,11 €** sind nicht abziehbar.
> - Wichtig: Die **Vorsteuer (38,07 €) ist trotzdem voll erstattbar**, unabhängig vom 70/30-Split.
>
> **DATEV-Buchung (SKR03):**
>
> | Soll | Haben | BU-Schlüssel | Betrag |
> |---|---|:---:|---:|
> | 4650 — Bewirtungskosten (70% abziehbar) | 1200 — Bank | 9 | 238,45 € |
>
> Konto 4650 ist im SKR03 vorhanden ✓. Falls du eine Bewirtungs-Notiz brauchst (Anlass, Teilnehmer), denk dran — das ist Pflicht für den Vorsteuerabzug; der Beleg allein reicht nicht. Soll ich dir die Bewirtungs-Notiz formulieren?

## Why this matters

Three things happen here that a casual GoogleSheet-Buchhaltung gets wrong constantly:

1. **The 70/30 rule applies to the net amount, not the gross.** A typical mistake is to multiply 238,45 × 0,7 = 166,92 and book that — wrong. The correct path is *net* × 0,7 = 140,27.
2. **VAT is fully recoverable.** Many SaaS-categorisation tools route Bewirtung through a "70% deductible" pipeline that also caps the Vorsteuer at 70%. That's a tax-payment to the Finanzamt that didn't have to happen.
3. **Bewirtungs-Notiz is mandatory.** § 14 UStG / § 4 Abs. 5 Nr. 2 EStG require it for the deduction to hold. Claude can prompt for it; a silent UI cannot.

The workflow shows that an LLM with the right tools is **better than a UI** for this kind of decision-heavy categorisation, because the LLM can flag the surrounding rules without being asked.

## Variations to try

- "und wenn ich es als Mitarbeiterbewirtung abrechne?" — Claude re-runs `apply_bewirtung_rule` with `is_employee_event=True`, getting 100 / 0 split, then re-resolves. The SKR account stays at 4650; only the deduction percentage changes.
- "ist das auch in SKR04 gleich?" — Claude re-runs `resolve_account_assignment` with `skr="SKR04"`; result switches to 6650 (Bewirtung) and 1800 (Bank).
- "was wäre, wenn ich bar bezahlt hätte?" — `payment_method="cash"` flips the contra to 1000 (SKR03) or 1600 (SKR04).
