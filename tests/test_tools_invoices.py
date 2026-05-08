"""Tests for the list_invoices tool."""

from __future__ import annotations

import json
from datetime import date

import pytest
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


async def test_list_invoices_production_raises_clear_error(server_prod: FastMCP) -> None:
    # FastMCP wraps tool exceptions in ToolError; the underlying message must still
    # mention that production mode isn't wired yet so the LLM can guide the user.
    with pytest.raises(ToolError, match="not yet wired"):
        await _call_list_invoices(server_prod)
