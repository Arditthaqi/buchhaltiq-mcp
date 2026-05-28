# Case Study — buchhaltiq-mcp

## TL;DR

A working Model Context Protocol server that lets Claude Desktop talk directly to a German SMB accounting backend. **Eleven tools** cover read access (invoices, customers, bank transactions, monthly P&L), VAT math (split, BU-key lookup, Bewirtung deduction), and full DATEV Kontierung (account, contra-account, debit/credit, BU-key). End-to-end tested against real Firestore data on May 8, 2026 — the developer's own restaurant.

The interesting part is not the tool count. It is the pattern: a SaaS vendor making its own product MCP-ready, with the same tool definitions running against deterministic fixtures in demo mode and against the live API in production mode. Demo mode keeps the public repository GDPR-safe; production mode is a single env-var flip away.

---

## The problem

German bookkeeping is one of the most rules-heavy verticals in the world. The Bewirtungsbeleg (entertainment receipt) deduction alone has six layers:

- 70% of the net amount is income-tax-deductible (§ 4 Abs. 5 Nr. 2 EStG)
- VAT is **fully** recoverable regardless of the 70/30 split — a routine source of categorisation errors
- A handwritten Bewirtungsnotiz is mandatory for the deduction; the receipt alone is not enough
- Restaurantbewirtung is generally 19% VAT
- Mitarbeiterbewirtung (in-house employee event) flips to 100% deductible
- The booking lands on different SKR03 / SKR04 accounts depending on the chart of accounts

Existing tools route this through dropdowns and form fields. The user either remembers which dropdown means what, or trusts a black-box ML categoriser. Both are bad: the dropdowns slow them down; the ML model cannot explain why it picked a category.

LLM-as-UI changes the substrate. The user types one sentence in German. Claude calls `apply_bewirtung_rule`, then `resolve_account_assignment`. The result is a Soll/Haben pair the user can post directly to DATEV, plus a plain-language explanation of why each rule fired.

---

## The pattern

The repository implements a deliberate pattern: **SaaS-makes-its-own-product-MCP-ready.**

Two modes share one tool definition:

- `BUCHHALTIQ_MCP_MODE=demo` — every tool reads from JSON fixtures in `data/`.
- `BUCHHALTIQ_MCP_MODE=production` — the same tool talks to `api.buchhaltiq.de` over `httpx.AsyncClient`.

Each tool's body is a clean if/else:

```python
if config.mode is Mode.DEMO:
    return _demo_implementation(...)
return await client.method(...)
```

The demo path keeps the public repo GDPR-safe — no real customer data flows through tests, CI, or the published workflows. The production path is what an actual operator runs against their own workspace.

The companion document `docs/BACKEND_ENDPOINTS_TO_ADD.md` keeps the legacy read-endpoint contract documented, while the newer BuchhaltIQ-aware month overview now has its own backend route under `/api/mcp/month-overview/{period_key}`. The MCP repo and the backend repo stay decoupled — the MCP repo owns its expectations, the backend repo owns the implementation.

---

## Architecture decisions worth defending

| Decision | Why |
|---|---|
| **Two-mode split** | The same code base serves as a public Open Source showcase **and** the actual production runtime. No fork, no drift. |
| **Decimal everywhere** | Money math in floats is malpractice. ROUND_HALF_UP at two places, single source of truth in `_money.py`. |
| **`posting_class=pnl` filter for monthly P&L** | Without it, every internal bank transfer counts as an expense. Real April 2026 number for the test user dropped from **53,507€ pauschal to 26,252€ relevant** — and the response carries an audit trail explaining what was excluded. |
| **Pydantic v2 with `extra="forbid"`** | Catches silent schema drift at deserialization. |
| **FastMCP + stdio transport only** | Desktop integration standard. No extra surface area to defend. |
| **Categorize-rule rationales** | Every match returns the rule that fired, so the LLM can explain its decision rather than just stating it — important for any auditor reviewing the books later. |
| **Tax-free category override** | If `category=miete_pacht` and the user passes `tax_rate=19`, the tool **forces** the rate to 0. Guards against a confused LLM accidentally adding VAT to a tax-free posting. |

---

## Validation

End-to-end tested on May 8, 2026 against the developer's own restaurant data in Firestore:

| Tool call | Real result |
|---|---|
| `list_invoices` | 1 paid invoice for April: Hotel Amerika, RE-2026-001, 1.281,00 € |
| `monthly_report(2026, 4)` | 1.281€ revenue, 26.252€ P&L expenses, -24.971€ profit, with 27.255€ across 13 transactions excluded as non-P&L |
| `accounting_month_overview("2026-04")` | BuchhaltIQ-aware split across Tagesberichte, invoice payments, standalone income, P&L expenses, VAT estimate, and DATEV readiness |
| `search_belege("METRO")` | 5 real METRO transactions across 3 weeks, all auto-categorised "Wareneinkauf & Material" |
| `resolve_account_assignment("wareneinkauf_material", "238.45")` | SKR03 3400/1200, BU-key 9, net 200.38€, tax 38.07€, validation valid |

126 unit tests on the MCP side (with `respx` for backend mocking), `ruff` clean. Demo-mode invariants verified separately so the public repo's CI does not depend on a backend running.

---

## What I would build next

Three buckets, prioritised:

1. **Receipt-photo pipeline.** Beleg-Foto → vision-model parse → automatic posting. Closing the manual-data-entry loop is the highest-leverage end-user feature; not yet built. Whether to use Claude Vision, a self-hosted vision model, or a structured-OCR provider is an open trade-off captured in the architecture roadmap.
2. **UStVA generator.** Monthly Umsatzsteuer-Voranmeldung is procedural and bureaucratic. A `generate_ustva(year, month)` tool would turn a 30-minute manual task into a one-sentence chat.
3. **Multi-tenant rollout.** Currently single-user (the developer's own account). A real productised version requires an Auftragsverarbeitungsvertrag with Anthropic, an opt-in flow in the BuchhaltIQ frontend, and the Privacy Policy update documented in `docs/PRIVACY.md`.

---

## Tech footprint

- **21 commits** on `main`, all Conventional-Commits style
- **Python 3.11 / 3.12 / 3.13** verified in CI
- **15 tools** across 10 modules under `src/buchhaltiq_mcp/tools/`
- **126 tests**, including respx-mocked backend integration tests for every wired tool
- **6 architecture / privacy / reference docs** (`PRIVACY.md`, `architecture.md`, `tools-reference.md`, `PRODUCTION_SETUP.md`, `BACKEND_ENDPOINTS_TO_ADD.md`, `CASE_STUDY.md` — this file)
- **6 conversational workflow walkthroughs** under `examples/workflows/`, each showing one realistic Claude-Desktop conversation with the underlying tool calls
- **MIT licensed**, MCP Inspector compatible

---

## What this proves

Three things this project is meant to demonstrate, in priority order:

1. **The "SaaS-makes-its-own-product-MCP-ready" pattern works at the architecture level**, not just in toy demos. A real backend, a real chart of accounts, real tax law, and real customer data — with the same tool definitions deployable in two modes that share zero behavioural drift.
2. **LLM-as-UI is the right substrate for high-rules-density verticals like accounting.** A categorisation tool that returns its rule's rationale, a Bewirtung tool that flags the Vorsteuer trap, an audit trail in the monthly P&L — these are surfaces a deterministic UI does not naturally provide.
3. **The work is shippable, not aspirational.** End-to-end tested. Tests green. Documentation in sync with code. Privacy posture documented. Production wiring complete.

---

## Repository

The complete source — code, tests, fixtures, docs, examples — is at `github.com/Arditthaqi/buchhaltiq-mcp` (replace once published).

Built by [Ardit Thaqi](https://bornsoftware.de) for [Born — Theoretical Software](https://bornsoftware.de), May 2026.
