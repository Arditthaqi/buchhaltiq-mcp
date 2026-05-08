"""Tests for the list_invoices tool."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.models import InvoiceStatus
from buchhaltiq_mcp.tools import invoices as invoices_tool


async def _call_list_invoices(server: FastMCP, **kwargs: object) -> list[dict]:
    """Invoke the registered list_invoices tool and unwrap the result payload.

    FastMCP returns ``(content_blocks, structured)`` from ``call_tool``. We accept
    either the structured payload or fall back to parsing the JSON text block.
    """
    result = await server.call_tool("list_invoices", kwargs)
    if isinstance(result, tuple) and len(result) >= 2:
        content, structured = result[0], result[1]
    else:
        content, structured = result, None

    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    if isinstance(structured, list):
        return structured

    text_block = next(block for block in content if getattr(block, "type", None) == "text")
    return json.loads(text_block.text)


@pytest.fixture
def server_demo(demo_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    invoices_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    invoices_tool.register(server, production_config)
    return server


async def test_list_invoices_demo_returns_all_by_default(server_demo: FastMCP) -> None:
    rows = await _call_list_invoices(server_demo)
    assert len(rows) >= 5
    assert all("id" in r and "customer_id" in r for r in rows)


async def test_list_invoices_demo_filters_by_status(server_demo: FastMCP) -> None:
    rows = await _call_list_invoices(server_demo, status=InvoiceStatus.OVERDUE.value)
    assert len(rows) >= 1
    assert all(r["status"] == "overdue" for r in rows)


async def test_list_invoices_demo_filters_by_customer(server_demo: FastMCP) -> None:
    rows = await _call_list_invoices(server_demo, customer_id="cust_001")
    assert len(rows) >= 1
    assert all(r["customer_id"] == "cust_001" for r in rows)


async def test_list_invoices_demo_filters_by_date_range(server_demo: FastMCP) -> None:
    rows = await _call_list_invoices(
        server_demo,
        issued_from=date(2026, 3, 1).isoformat(),
        issued_to=date(2026, 3, 31).isoformat(),
    )
    assert all("2026-03" in r["issue_date"] for r in rows)


async def test_list_invoices_demo_respects_limit(server_demo: FastMCP) -> None:
    rows = await _call_list_invoices(server_demo, limit=2)
    assert len(rows) == 2


@respx.mock
async def test_list_invoices_production_calls_backend_and_returns_items(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/user-invoices/list"
    respx.get(backend_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "inv_real_001",
                        "invoice_number": "2026-001",
                        "customer_id": "cust_external_42",
                        "customer_name": "Restaurant Acme",
                        "issue_date": "2026-03-04",
                        "due_date": "2026-04-03",
                        "status": "open",
                        "total_net": "200.38",
                        "total_gross": "238.45",
                        "currency": "EUR",
                        "description": "",
                    }
                ],
                "count": 1,
            },
        )
    )

    rows = await _call_list_invoices(server_prod, status=InvoiceStatus.OPEN.value)
    assert len(rows) == 1
    assert rows[0]["id"] == "inv_real_001"
    assert rows[0]["status"] == "open"


@respx.mock
async def test_list_invoices_production_propagates_backend_5xx(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/user-invoices/list"
    respx.get(backend_url).mock(return_value=httpx.Response(503, text="Firestore unavailable"))

    with pytest.raises(ToolError, match="503"):
        await _call_list_invoices(server_prod)
