# Example Workflows

Each workflow walks through one realistic Claude Desktop conversation and shows the tools that fire under the hood. They are written against the demo fixtures shipped under [`../../data/`](../../data/), so anyone can reproduce them locally with `BUCHHALTIQ_MCP_MODE=demo` (the default).

| Workflow | Scenario | Tools used |
|---|---|---|
| [01 — Overdue invoices for Q1](01_overdue_invoices_for_q1.md) | "Show me everything that's overdue from the first quarter." | `list_invoices` |
| [02 — Monthly summary](02_monthly_summary.md) | "Give me a one-paragraph rundown of how March looked." | `monthly_report` |
| [03 — Categorize a batch of new receipts](03_categorize_uncategorized_belege.md) | "I just exported these transactions from my bank — please tag them." | `categorize_transaction` (×n) |
| [04 — Customer overview](04_customer_overview.md) | "Tell me everything you know about cust_002." | `get_customer`, `list_invoices` |

## How to read a workflow file

Every file follows the same shape:

1. **Scenario** — who is asking and why.
2. **The prompt** — the exact natural-language sentence the user types into Claude.
3. **Under the hood** — which tools Claude calls, with which arguments. These are real arguments, not hypothetical ones.
4. **Sample response** — a plausible answer Claude composes from the tool output. Wording will vary in practice; the *content* is reproducible from the fixtures.
5. **Why this matters** — the productivity payoff over doing it by hand.

## How to reproduce locally

After installing the server (see top-level `README.md`), point Claude Desktop at it and paste the prompt from any workflow into a fresh conversation. The MCP Inspector (`npx @modelcontextprotocol/inspector python -m buchhaltiq_mcp`) is a faster way to see the raw tool calls and responses without going through the LLM.
