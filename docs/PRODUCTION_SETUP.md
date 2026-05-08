# Production-Mode Setup

This document explains how to point the MCP server at a running BuchhaltIQ backend so that the relevant tools call live API endpoints instead of fixture data. Today this enables **two tools** end-to-end against the real backend:

- `validate_datev_account` — wraps `GET /api/accounting/validate/{skr}/{account}`
- `resolve_account_assignment` — wraps `POST /api/accounting/resolve`

The other nine tools either fall back to in-process logic (the tax-math helpers) or still raise `ProductionNotImplementedError` because their backend routes do not yet exist (`list_invoices`, `get_customer`, `search_belege`, `monthly_report`). See [Status](#status) below.

## Prerequisites

1. The BuchhaltIQ backend running and reachable from the machine that runs the MCP server. For local development this means `uvicorn` on `localhost:8080` (the default `PORT` in the backend's `app/main.py`).
2. The MCP server installed in editable mode (`pip install -e ".[dev]"`).
3. Claude Desktop (or any MCP client) configured to launch this server.

The validate and resolve endpoints are currently **public** on the backend — no Authorization header required. The Authorization plumbing is already in place in `BuchhaltIQClient` for when read endpoints with Firebase-token auth land later.

## Configuration

The server is driven by three environment variables:

| Variable | Required for production | Example | Notes |
|---|---|---|---|
| `BUCHHALTIQ_MCP_MODE` | yes | `production` | Default is `demo`. Set this to flip the wired tools to call the backend. |
| `BUCHHALTIQ_API_BASE_URL` | yes | `http://localhost:8080` | No trailing slash. Strip the `/api/...` prefix — that lives in the client. |
| `BUCHHALTIQ_API_KEY` | **required** for the four read endpoints | `<firebase id token>` | A Firebase ID token belonging to the operator's BuchhaltIQ account. Tokens expire after 1 hour — for repeated testing, refresh manually. The validate / resolve endpoints stay public, so this is only required for `list_invoices`, `get_customer`, `search_belege`, `monthly_report`. |

## Getting a Firebase ID token for testing

For a one-shot test from your own BuchhaltIQ account, the simplest path is to grab a token via the Firebase SDK in any environment that has your account credentials:

```python
import firebase_admin
from firebase_admin import auth, credentials

cred = credentials.Certificate("/path/to/service-account-key.json")
firebase_admin.initialize_app(cred)

# This requires an existing Firebase user UID — generate a custom token,
# exchange it via the REST API for an ID token, and you have your Bearer.
custom_token = auth.create_custom_token("<your-firebase-uid>")
```

For interactive testing the Flutter app or any client that already logs you in is the fastest source of an ID token (open the network panel, copy the Bearer header).

## Claude Desktop wiring

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "buchhaltiq": {
      "command": "/absolute/path/to/.venv/bin/buchhaltiq-mcp",
      "env": {
        "BUCHHALTIQ_MCP_MODE": "production",
        "BUCHHALTIQ_API_BASE_URL": "http://localhost:8080"
      }
    }
  }
}
```

Restart Claude Desktop after the edit.

## Smoke test (without Claude Desktop)

The fastest way to confirm the wiring works is the MCP Inspector — it gives you a web UI that calls the tools directly:

```bash
# In one terminal: start the backend.
cd /path/to/BuchhaltIQ-Backend
uvicorn app.main:app --reload --port 8080

# In another terminal: start the MCP server in production mode under Inspector.
cd /path/to/buchhaltiq-mcp
BUCHHALTIQ_MCP_MODE=production \
BUCHHALTIQ_API_BASE_URL=http://localhost:8080 \
  npx @modelcontextprotocol/inspector python -m buchhaltiq_mcp
```

Open the Inspector URL it prints, switch to the Tools tab, and run:

- **`validate_datev_account`** with `skr=SKR03`, `account=4650` → expect `is_valid=true` and a `title` field carrying the DATEV-reference line.
- **`resolve_account_assignment`** with `category_id=wareneinkauf_material`, `amount_gross="238.45"`, `payment_method=bank`, `skr=SKR03` → expect a complete booking pair (account, contra_account, bu_key, debit/credit, Decimal split).

If those return successfully, the production wiring is correct.

## Production-mode response shape

The two wired tools return the **same top-level keys** in production as in demo mode, plus a few backend-only extras:

- `validate_datev_account` (production) additionally returns `warnings` and the full `datev_references` list. `suggestions` is always empty in production because the backend has no fuzzy-match heuristic.
- `resolve_account_assignment` (production) additionally returns `posting_class` and `bwa_relevant` from the backend. The `account_title` and `contra_account_title` keys are still resolved from the local `data/datev_accounts.json` fixture as a UX nicety since the backend does not return them.

## Status

| Tool | Production today | Notes |
|---|---|---|
| `extract_vat_from_receipt` | ✅ same as demo (pure math) | Math is decentralised in `_money.py`; no backend dependency. |
| `map_tax_rate_to_bu_key` | ✅ same as demo (pure lookup) | Same. |
| `apply_bewirtung_rule` | ✅ same as demo (pure math) | Same. |
| `split_mixed_tax_receipt` | ✅ same as demo (pure math) | Same. |
| `categorize_transaction` | ✅ same as demo (rule-based) | Rule engine has no backend; works identically in both modes. |
| `validate_datev_account` | ✅ **wired to `GET /api/accounting/validate`** | Falls through to backend; returns enriched response. |
| `resolve_account_assignment` | ✅ **wired to `POST /api/accounting/resolve`** | Falls through to backend; returns enriched response. |
| `list_invoices` | ✅ **wired to `GET /api/user-invoices/list`** | Requires the backend route block from [`BACKEND_ENDPOINTS_TO_ADD.md`](BACKEND_ENDPOINTS_TO_ADD.md). Firebase token auth. |
| `get_customer` | ✅ **wired to `GET /api/user-invoices/customers`** | Same; aggregate fetched, filtered client-side by id. |
| `search_belege` | ✅ **wired to `GET /api/user-invoices/transactions`** | Same; bank transactions projected as Belege. |
| `monthly_report` | ✅ **wired to `GET /api/user-invoices/monthly-report`** | Same; aggregation runs on the backend. |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `BuchhaltIQAPIError: 503 from .../validate/...: DATEV ref unavailable` | Backend cannot find its `data/datev_kontenrahmen` reference files. | Verify the backend's data directory and paths. |
| `ToolError: Error executing tool ...: Connection refused` | Backend is not running on the configured base URL. | Start `uvicorn` or fix `BUCHHALTIQ_API_BASE_URL`. |
| `BuchhaltIQAPIError: 400 from .../resolve: Unknown category_id` | Category exists in MCP `data/categories.json` but not in the backend's `category_definitions.json`. | Either add the category to the backend, or use a category the backend already knows. |
| The two wired endpoints reject your token | The endpoints are public today; sending an Authorization header is harmless but unnecessary. | If you accidentally set a malformed token via `BUCHHALTIQ_API_KEY` and a private endpoint later rejects it, unset the variable. |
