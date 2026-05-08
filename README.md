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

## Status

**Phase 1 — work in progress.** Currently implemented:

- ✅ Mode-switching configuration (env-driven)
- ✅ `list_invoices` (demo mode complete; production stub raises a clear error)
- ✅ `get_customer` (demo mode complete; production stub raises a clear error)
- ✅ Pydantic models for invoices, customers, receipts
- ✅ German-SMB demo fixtures (5 customers, 8 invoices, 6 receipts)

Planned for Phase 1 completion:

- `search_belege` — full-text search over receipts
- `monthly_report` — BWA-style monthly summary
- `categorize_transaction` — smart-categorization (BuchhaltIQ's open-sourced rules)

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
│       └── customers.py       get_customer
├── data/                      Demo fixtures (German SMB context).
│   ├── customers.json
│   ├── invoices.json
│   └── belege.json
├── tests/                     pytest suite.
└── docs/                      (work in progress)
```

## License

MIT — see [`LICENSE`](LICENSE). Built by [Born — Theoretical Software](https://bornsoftware.de).
