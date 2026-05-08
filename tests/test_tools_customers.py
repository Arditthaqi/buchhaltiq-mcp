"""Tests for the get_customer tool."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import customers as customers_tool


async def _call_get_customer(server: FastMCP, **kwargs: object) -> dict:
    """Invoke the registered get_customer tool and unwrap the result payload."""
    result = await server.call_tool("get_customer", kwargs)
    if isinstance(result, tuple) and len(result) >= 2:
        content, structured = result[0], result[1]
    else:
        content, structured = result, None

    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    if isinstance(structured, dict):
        return structured

    text_block = next(block for block in content if getattr(block, "type", None) == "text")
    return json.loads(text_block.text)


@pytest.fixture
def server_demo(demo_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    customers_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    customers_tool.register(server, production_config)
    return server


async def test_get_customer_demo_returns_known_customer(server_demo: FastMCP) -> None:
    row = await _call_get_customer(server_demo, customer_id="cust_001")
    assert row["id"] == "cust_001"
    assert "Schinderhannes" in row["name"]
    assert row["country"] == "DE"


async def test_get_customer_demo_unknown_id_raises_not_found(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="No customer with id"):
        await _call_get_customer(server_demo, customer_id="cust_does_not_exist")


async def test_get_customer_demo_empty_id_raises_validation(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="non-empty string"):
        await _call_get_customer(server_demo, customer_id="   ")


@respx.mock
async def test_get_customer_production_filters_backend_aggregate(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/user-invoices/customers"
    respx.get(backend_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "cust_external_42",
                        "name": "Restaurant Acme",
                        "company_name": None,
                        "contact_email": "info@acme.example",
                        "city": "Berlin",
                        "country": "DE",
                        "vat_id": None,
                        "tax_number": None,
                    },
                    {
                        "id": "cust_external_43",
                        "name": "Café Beta",
                        "company_name": None,
                        "contact_email": None,
                        "city": "München",
                        "country": "DE",
                        "vat_id": None,
                        "tax_number": None,
                    },
                ],
                "count": 2,
            },
        )
    )

    row = await _call_get_customer(server_prod, customer_id="cust_external_43")
    assert row["id"] == "cust_external_43"
    assert row["name"] == "Café Beta"


@respx.mock
async def test_get_customer_production_unknown_id_raises(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/user-invoices/customers"
    respx.get(backend_url).mock(return_value=httpx.Response(200, json={"items": [], "count": 0}))

    with pytest.raises(ToolError, match="No customer with id"):
        await _call_get_customer(server_prod, customer_id="cust_nope")
