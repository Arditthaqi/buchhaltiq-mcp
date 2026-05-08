"""Tests for the search_belege tool."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import belege as belege_tool


async def _call_search_belege(server: FastMCP, **kwargs: object) -> list[dict]:
    """Invoke the registered search_belege tool and unwrap the result payload."""
    result = await server.call_tool("search_belege", kwargs)
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
    belege_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    belege_tool.register(server, production_config)
    return server


async def test_search_belege_demo_matches_vendor(server_demo: FastMCP) -> None:
    rows = await _call_search_belege(server_demo, query="METRO")
    assert len(rows) >= 1
    assert all("METRO" in r["vendor"] for r in rows)


async def test_search_belege_demo_matches_description(server_demo: FastMCP) -> None:
    rows = await _call_search_belege(server_demo, query="Diesel")
    assert len(rows) >= 1
    assert any("Diesel" in r["description"] for r in rows)


async def test_search_belege_demo_is_case_insensitive(server_demo: FastMCP) -> None:
    upper = await _call_search_belege(server_demo, query="TELEKOM")
    lower = await _call_search_belege(server_demo, query="telekom")
    assert {r["id"] for r in upper} == {r["id"] for r in lower}
    assert len(upper) >= 1


async def test_search_belege_demo_respects_limit(server_demo: FastMCP) -> None:
    rows = await _call_search_belege(server_demo, query="e", limit=2)
    assert len(rows) <= 2


async def test_search_belege_demo_empty_query_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="non-empty string"):
        await _call_search_belege(server_demo, query="   ")


async def test_search_belege_demo_no_match_returns_empty(server_demo: FastMCP) -> None:
    rows = await _call_search_belege(server_demo, query="absolut-nicht-im-fixture")
    assert rows == []


@respx.mock
async def test_search_belege_production_calls_transactions_endpoint(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/user-invoices/transactions"
    respx.get(backend_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "tx_real_001",
                        "issue_date": "2026-03-10",
                        "vendor": "METRO Cash & Carry GmbH",
                        "amount_gross": "-238.45",
                        "category": None,
                        "description": "Wareneinkauf METRO Filiale 42",
                    }
                ],
                "count": 1,
            },
        )
    )
    rows = await _call_search_belege(server_prod, query="METRO")
    assert len(rows) == 1
    assert "METRO" in rows[0]["vendor"]
