# buchhaltiq-mcp

> Model Context Protocol server for **[BuchhaltIQ](https://buchhaltiq.de)** — the mobile-first accounting product for German SMBs by [Born — Theoretical Software](https://bornsoftware.de).

![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-1B2A4E)
![License](https://img.shields.io/badge/license-MIT-D17B0F)
![MCP](https://img.shields.io/badge/protocol-MCP-2D8A87)

This repository demonstrates the **"SaaS-makes-its-own-product-MCP-ready"** pattern: a software vendor exposing its own product's domain (invoices, customers, receipts, monthly reports) over the Model Context Protocol so that Claude Desktop and other MCP clients can drive it directly.

The server ships in two modes: a **demo mode** that runs entirely on local JSON fixtures (no API key, no account, fully reproducible), and a **production mode** that talks to the real BuchhaltIQ API.

## Why two modes?

| Mode | When to use it | Data source |
|---|---|---|
| `demo` (default) | Trying out the server, building example workflows, public reproduction in this repo's tests and CI. | Realistic German-SMB fixtures shipped under [`data/`](data/) — restaurants, bakeries, tax offices. |
| `production` | Driving the actual BuchhaltIQ workspace from Claude. Requires a `BUCHHALTIQ_API_KEY` and the `production` mode flag. | The real BuchhaltIQ REST API at `api.buchhaltiq.de`. |

Demo mode keeps the public repository risk-free: no real customer data ever flows through example workflows, GitHub Actions, or third-party demos. Production mode lets a BuchhaltIQ user point the same MCP server at their live workspace.

For a detailed breakdown of what data flows where — and the GDPR/DSGVO obligations that apply once production mode is enabled — see [`docs/PRIVACY.md`](docs/PRIVACY.md).

For end-to-end conversational examples (overdue invoices, monthly summaries, batch categorization, customer briefings) see [`examples/workflows/`](examples/workflows/).

For the system design behind the server — components, the demo↔production mode switch, the seven-step pattern for adding a tool — see [`docs/architecture.md`](docs/architecture.md).

For an exhaustive parameter and response reference for every tool, see [`docs/tools-reference.md`](docs/tools-reference.md).

## Status

**Phase 1 — feature-complete in demo mode.** All five tools ship with demo-mode implementations and clear production stubs:

- ✅ Mode-switching configuration (env-driven)
- ✅ `list_invoices` — list invoices with status / customer / date-range filters
- ✅ `get_customer` — single-customer detail lookup
- ✅ `search_belege` — full-text search over receipts
- ✅ `monthly_report` — BWA-style monthly P&L summary
- ✅ `categorize_transaction` — explainable rule-based German-accounting categorization
- ✅ `extract_vat_from_receipt` — split gross into net + VAT (0/7/19%, Decimal precision)
- ✅ `map_tax_rate_to_bu_key` — DATEV BU-key lookup for Vorsteuer / Umsatzsteuer
- ✅ `validate_datev_account` — verify SKR03 / SKR04 account numbers + suggest near-matches
- ✅ `apply_bewirtung_rule` — German 70/30 entertainment-deduction rule with full Vorsteuer recovery
- ✅ `split_mixed_tax_receipt` — split a multi-rate receipt into per-rate buckets with sum validation
- ✅ Pydantic models for invoices, customers, receipts, monthly reports, DATEV accounts
- ✅ German-SMB demo fixtures (5 customers, 8 invoices, 6 receipts, 26 SKR accounts)

Each tool's production-mode pathway raises `ProductionNotImplementedError` with a message guiding the operator back to demo mode until the live BuchhaltIQ API binding lands in Phase 2.

## Quick Start

```bash
# Clone + dev install
git clone https://github.com/Arditthaqi/buchhaltiq-mcp.git
cd buchhaltiq-mcp
pip install -e ".[dev]"

# Run tests
pytest

# Start the server in demo mode (default)
python -m buchhaltiq_mcp
```

To wire it into Claude Desktop, drop this snippet into `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "buchhaltiq": {
      "command": "buchhaltiq-mcp"
    }
  }
}
```

For production mode, set the env vars:

```bash
export BUCHHALTIQ_MCP_MODE=production
export BUCHHALTIQ_API_KEY="your-key-here"
buchhaltiq-mcp
```

## Project Structure

```text
buchhaltiq-mcp/
├── README.md
├── pyproject.toml
├── .env.example
├── src/buchhaltiq_mcp/
│   ├── __init__.py
│   ├── __main__.py            Entry point: `python -m buchhaltiq_mcp`.
│   ├── server.py              FastMCP server factory.
│   ├── config.py              Mode + API-key resolution from env.
│   ├── models.py              Pydantic v2 domain models.
│   ├── fixtures.py            JSON fixture loader for demo mode.
│   ├── exceptions.py
│   └── tools/
│       ├── __init__.py        register_all(server, config)
│       ├── invoices.py        list_invoices
│       ├── customers.py       get_customer
│       ├── belege.py          search_belege
│       ├── reports.py         monthly_report
│       ├── categorize.py      categorize_transaction
│       ├── vat.py             extract_vat_from_receipt, map_tax_rate_to_bu_key
│       ├── datev.py           validate_datev_account
│       ├── bewirtung.py       apply_bewirtung_rule
│       └── split.py           split_mixed_tax_receipt
├── data/                      Demo fixtures (German SMB context).
│   ├── customers.json
│   ├── invoices.json
│   └── belege.json
├── tests/                     pytest suite.
└── docs/                      (work in progress)
```

## License

MIT — see [`LICENSE`](LICENSE). Built by [Born — Theoretical Software](https://bornsoftware.de).
