# Workflow 06 — Gemischter Supermarkt-Beleg sauber zerlegen

## Scenario

A bakery owner returns from METRO with a single 77,30 € receipt that contains both food (7% VAT) and cleaning supplies (19% VAT). One receipt, two tax rates, two postings. Either she sits down with a calculator and the SKR03 reference, or she hands the line items to Claude and gets back two ready-to-post bookings plus a sanity check that the splits add up.

This is the workflow where `split_mixed_tax_receipt` and `resolve_account_assignment` compose into something the user could not easily get from a UI.

## The prompt

> Ich habe einen METRO-Beleg über 77,30 €. Davon waren 53,50 € Lebensmittel (7% MwSt) und 23,80 € Reinigungsmaterial (19% MwSt). Buch mir das sauber auf, mit DATEV-Konten in SKR03.

## Under the hood

Two kinds of calls happen here. First the split, then a per-rate resolution:

```
# 1. Split the receipt and validate the sum.
split_mixed_tax_receipt(
    positions=[
        {"amount_gross": "53.50", "tax_rate": "7",  "description": "Lebensmittel"},
        {"amount_gross": "23.80", "tax_rate": "19", "description": "Reinigungsmaterial"},
    ],
    expected_total_gross="77.30",
)
# → has_mixed_tax=true, total_gross=77.30, warnings=[]
#   breakdown_by_rate:
#     "7":  {gross=53.50, net=50.00, tax=3.50, ...}
#     "19": {gross=23.80, net=20.00, tax=3.80, ...}

# 2. Resolve the 7% leg as Wareneinkauf.
resolve_account_assignment(
    category_id="wareneinkauf_material",
    amount_gross="53.50",
    tax_rate="7",
    payment_method="cash",
    skr="SKR03",
)
# → account=3400, contra=1000, bu_key=8 (7% Vorsteuer)

# 3. Resolve the 19% leg as Bürobedarf / Geringwertige WG.
resolve_account_assignment(
    category_id="buerobedarf",
    amount_gross="23.80",
    tax_rate="19",
    payment_method="cash",
    skr="SKR03",
)
# → account=4980, contra=1000, bu_key=9 (19% Vorsteuer)
```

## Sample response

> **Beleg-Aufteilung — METRO 77,30 € gesamt:**
>
> | Rate | Brutto | Netto | Steuer | Positionen |
> |---:|---:|---:|---:|:---:|
> | 7% | 53,50 € | 50,00 € | 3,50 € | 1 (Lebensmittel) |
> | 19% | 23,80 € | 20,00 € | 3,80 € | 1 (Reiniger) |
> | **Gesamt** | **77,30 €** | **70,00 €** | **7,30 €** | **2** |
>
> Summen passen — keine Warnung von der Validierung.
>
> **Zwei DATEV-Buchungen (SKR03), beide auf dieselbe Kasse:**
>
> | # | Soll | Haben | BU-Schlüssel | Betrag |
> |---|---|---|:---:|---:|
> | 1 | 3400 — Wareneingang 19% Vorsteuer¹ | 1000 — Kasse | 8 | 53,50 € |
> | 2 | 4980 — Sonstige Aufwendungen / Bürobedarf | 1000 — Kasse | 9 | 23,80 € |
>
> ¹ Hinweis: SKR03-Konto 3400 heißt traditionell "Wareneingang 19% Vorsteuer", die 7%-Buchung läuft trotzdem hier rein, der BU-Schlüssel **8** signalisiert dem DATEV-System aber den ermäßigten Steuersatz. Die Konto-Bezeichnung ist historisch, der BU-Key ist die wahre Quelle der Steuerlogik.
>
> Willst du, dass ich Buchung 1 stattdessen auf ein dediziertes Lebensmittel-Konto (z.B. 3300) umroutiere? Das wäre kontentechnisch sauberer, ist aber bei kleinen SMBs unüblich.

## Why this matters

Three subtleties this workflow surfaces that a generic categoriser would miss:

1. **Sum-check before posting.** The `expected_total_gross` argument turns the tool into a guard rail: if the user mistypes a position by one cent, the warning fires and Claude can ask before posting (rather than silently producing a 1-cent-off booking).
2. **BU-Key carries the real tax-rate semantics.** SKR03 has historic account names that pre-date the 7/19 split (e.g. "3400 — Wareneingang 19% Vorsteuer"). The BU-key is what tells DATEV which rate to actually apply. The LLM, looking at the result, knows to flag this to the user — a silent UI doesn't.
3. **Per-rate routing requires per-rate categories.** This is the kind of decision a UI typically shoves at the user with a dropdown. Claude makes it explicit and offers to route differently.

## Variations to try

- "ich habe noch einen Pfand-Posten 0,50 € dazu" — Claude re-runs the split with three positions including the 0% Pfand line, then resolves three bookings.
- "und wenn das mit Karte gezahlt war?" — `payment_method="bank"` flips the contra from 1000 (Kasse) to 1200 (Bank) on both bookings.
- "kannst du das als CSV ausgeben, das ich in Excel pasten kann?" — pure composition; the structured tool outputs are already easy to render.
