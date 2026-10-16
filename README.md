# buchhaltiq-mcp

> Model Context Protocol server for **[BuchhaltIQ](https://buchhaltiq.de)** — the mobile-first accounting product for German SMBs by [Born — Theoretical Software](https://bornsoftware.de).

![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-1B2A4E)
![Tests](https://img.shields.io/badge/tests-126%20passing-3a8a3a)
![License](https://img.shields.io/badge/license-MIT-D17B0F)
![MCP](https://img.shields.io/badge/protocol-MCP-2D8A87)

`buchhaltiq-mcp` exposes a German-SMB accounting domain — invoices, customers, bank-transaction Belege, BuchhaltIQ-aware month overview, HR time tracking, full DATEV Kontierung — as fifteen Model Context Protocol tools. Drop it into Claude Desktop and ask in natural German: *"Wie war mein April? Erklär mir auch die ausgeschlossenen Aufwendungen."* Claude calls the relevant tools, gets real data back, and answers.

The server ships in **two modes** that share one tool definition: a `demo` mode against deterministic JSON fixtures (no API key, no account, fully reproducible) and a `production` mode against the live BuchhaltIQ backend. End-to-end validated against real Firestore data on May 8, 2026 — see [`docs/CASE_STUDY.md`](docs/CASE_STUDY.md).

## Why two modes?

| Mode | When | Data source |
|---|---|---|
| `demo` (default) | Trying out the server, running tests, shipping public examples. | Realistic German-SMB fixtures under [`data/`](data/) — restaurants, bakeries, tax offices, plus 26 real SKR03/SKR04 accounts and 7 BuchhaltIQ category mappings. |
| `production` | Driving a live BuchhaltIQ workspace. Requires the backend running and a Firebase ID token. | The live BuchhaltIQ REST API. |

Demo mode keeps the public repository GDPR-safe — no real customer data flows through the test suite, GitHub Actions, or the example workflows. Production mode is a single env-var flip away.

> **Production note:** demo mode works from this repository alone. Production mode
> requires the BuchhaltIQ backend to expose the corresponding routes. In
> particular, `accounting_month_overview` needs
> `GET /api/mcp/month-overview/{period_key}` to be deployed in the backend;
> otherwise the MCP tool will correctly fail with the backend's HTTP error.

## The fifteen tools

| | Tool | What it does |
|---|---|---|
| 📑 | `list_invoices` | List invoices with status / customer / date-range filters, newest first |
| 👤 | `get_customer` | Fetch a single customer by ID |
| 🔍 | `search_belege` | Substring search over receipts (vendor + description), case-insensitive |
| 📊 | `monthly_report` | BWA-style P&L summary; in production mode the same calculation as `accounting_month_overview` (Tagesberichte, invoice payments, EÜR tax payments by cash flow) |
| 📈 | `accounting_month_overview` | BuchhaltIQ-aware month overview: Tagesberichte, invoice payments, standalone income, P&L expenses, VAT estimate, DATEV readiness |
| 👥 | `list_employees` | List employees with status / employment-type filters and field-minimized HR data |
| ⏱️ | `get_employee_work_summary` | One employee's monthly shift count, true work-day count, net hours, absences, and estimated wage |
| 🗓️ | `hr_month_overview` | HR month overview across employees: shifts vs work days, hours, absences, payroll status |
| 🏷️ | `categorize_transaction` | Rule-based vendor → German-accounting category, with the rule's rationale returned alongside |
| 💶 | `extract_vat_from_receipt` | Split a gross amount into net + VAT at 0/7/19%, Decimal-precise with ROUND_HALF_UP |
| 🔑 | `map_tax_rate_to_bu_key` | DATEV BU-Schlüssel lookup (2/3/8/9/40) for purchase vs sales side |
| ✅ | `validate_datev_account` | Verify SKR03/SKR04 account numbers; suggest near-matches on miss |
| 🍴 | `apply_bewirtung_rule` | German § 4 Abs. 5 Nr. 2 EStG entertainment-deduction rule with full Vorsteuer recovery — flags the trap that the 70/30 split applies to income-tax only |
| 🧾 | `split_mixed_tax_receipt` | Aggregate per-rate breakdown of a multi-rate receipt (the canonical METRO run with 7% food + 19% non-food + 0% Pfand) |
| 📚 | `resolve_account_assignment` | Full DATEV Kontierung from a BuchhaltIQ category: account, contra-account, BU-key, debit/credit side, Decimal net/tax/gross |

Full parameter reference in [`docs/tools-reference.md`](docs/tools-reference.md).

## Quick Start

```bash
# Clone + dev install
git clone https://github.com/Arditthaqi/buchhaltiq-mcp.git
cd buchhaltiq-mcp
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the test suite (126 tests, demo mode)
pytest

# Start the server in demo mode (default)
python -m buchhaltiq_mcp
```

To wire it into Claude Desktop, drop this into `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "buchhaltiq": {
      "command": "/absolute/path/to/.venv/bin/buchhaltiq-mcp"
    }
  }
}
```

Restart Claude Desktop and ask: *"Zeig mir die überfälligen Rechnungen aus Q1 2026."*

For production mode (live backend), see [`docs/PRODUCTION_SETUP.md`](docs/PRODUCTION_SETUP.md). For the legacy read-route contract and the newer month-overview backend requirement, see [`docs/BACKEND_ENDPOINTS_TO_ADD.md`](docs/BACKEND_ENDPOINTS_TO_ADD.md).

## Documentation map

| Doc | What you get |
|---|---|
| [`docs/CASE_STUDY.md`](docs/CASE_STUDY.md) | Narrative writeup: why the project exists, architecture decisions, May 8 validation, what's next |
| [`docs/TARGET_ARCHITECTURE.md`](docs/TARGET_ARCHITECTURE.md) | What a production-grade multi-tenant deployment looks like; phased migration path |
| [`docs/architecture.md`](docs/architecture.md) | System design + Mermaid diagram, the seven-step pattern for adding a tool |
| [`docs/tools-reference.md`](docs/tools-reference.md) | Exhaustive parameter / response / error reference for every tool |
| [`docs/PRIVACY.md`](docs/PRIVACY.md) | Data flow + GDPR / DSGVO obligations table |
| [`docs/PRODUCTION_SETUP.md`](docs/PRODUCTION_SETUP.md) | Env vars, smoke test, status of which tools are wired today |
| [`docs/BACKEND_ENDPOINTS_TO_ADD.md`](docs/BACKEND_ENDPOINTS_TO_ADD.md) | Legacy read-route contract plus the new month-overview backend route requirement |
| [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md) | 3-minute Loom storyboard |
| [`examples/workflows/`](examples/workflows/) | Six end-to-end conversational walkthroughs (overdue invoices, monthly summary, batch categorisation, customer briefing, Bewirtung booking, mixed-rate supermarket receipt) |

## Project Structure

```text
buchhaltiq-mcp/
├── README.md                    you are here
├── pyproject.toml               FastMCP + httpx + pydantic + ruff + pytest
├── .env.example
├── src/buchhaltiq_mcp/
│   ├── __main__.py              python -m buchhaltiq_mcp
│   ├── server.py                FastMCP factory
│   ├── config.py                mode + base-url + api-key from env
│   ├── client.py                async httpx wrapper for the backend
│   ├── _money.py                shared Decimal helpers (parse, round, split_gross)
│   ├── models.py                Pydantic v2 domain
│   ├── fixtures.py              JSON fixture loader for demo mode
│   ├── exceptions.py            BuchhaltIQError, NotFoundError, ProductionNotImplementedError
│   └── tools/                   one module per domain, each with a register() entry point
│       ├── invoices.py          list_invoices
│       ├── customers.py         get_customer
│       ├── belege.py            search_belege
│       ├── reports.py           monthly_report, accounting_month_overview
│       ├── hr.py                list_employees, get_employee_work_summary, hr_month_overview
│       ├── categorize.py        categorize_transaction
│       ├── vat.py               extract_vat_from_receipt, map_tax_rate_to_bu_key
│       ├── datev.py             validate_datev_account
│       ├── bewirtung.py         apply_bewirtung_rule
│       ├── split.py             split_mixed_tax_receipt
│       └── accounting.py        resolve_account_assignment
├── data/
│   ├── customers.json           5 demo SMBs
│   ├── invoices.json            8 demo invoices across all lifecycle states
│   ├── belege.json              6 demo receipts with German categories
│   ├── datev_accounts.json      26 SKR03 / SKR04 account references
│   ├── categories.json          7 BuchhaltIQ accounting categories with SKR mapping
│   ├── month_overviews.json     BuchhaltIQ-aware accounting month overview fixture
│   └── hr_*.json                employee, time-entry, absence, and HR-month fixtures
├── tests/                       126 tests; respx-mocked production-mode integration tests
├── docs/                        case study, architecture, privacy, production-setup, demo-script
└── examples/workflows/          six conversational walkthroughs
```

## License

MIT — see [`LICENSE`](LICENSE). Built by [Born — Theoretical Software](https://bornsoftware.de).
