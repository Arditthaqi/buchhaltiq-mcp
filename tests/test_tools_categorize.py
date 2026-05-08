"""Tests for the categorize_transaction tool."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import categorize as categorize_tool


async def _call_categorize(server: FastMCP, **kwargs: object) -> dict:
    """Invoke the registered categorize_transaction tool and unwrap the payload."""
    result = await server.call_tool("categorize_transaction", kwargs)
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
    categorize_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    categorize_tool.register(server, production_config)
    return server


@pytest.mark.parametrize(
    ("vendor", "description", "expected_category"),
    [
        ("METRO Cash & Carry", "Großhandel Mehl, Hefe, Pizzakäse", "Wareneinkauf"),
        ("Telekom Deutschland", "Geschäftsanschluss DSL", "Telekommunikation"),
        ("Shell Tankstelle", "Diesel Sprinter", "Fahrzeugkosten"),
        ("Deutsche Post AG", "Briefporto Mahnungen", "Porto"),
        ("OBI Baumarkt", "Werkzeug + Reinigungsmaterial", "Geringwertige Wirtschaftsgüter"),
        ("DATEV eG", "Monatsgebühr Schnittstelle", "Buchhaltungssoftware"),
        ("Deutsche Bahn", "ICE Berlin-München", "Reisekosten"),
    ],
)
async def test_categorize_recognizes_known_vendors(
    server_demo: FastMCP,
    vendor: str,
    description: str,
    expected_category: str,
) -> None:
    result = await _call_categorize(
        server_demo, vendor=vendor, description=description, amount_gross="100.00"
    )
    assert result["category"] == expected_category
    assert result["confidence"] == "rule_based"
    assert result["matched_rule"]  # non-empty rationale


async def test_categorize_falls_back_for_unknown_vendor(server_demo: FastMCP) -> None:
    result = await _call_categorize(
        server_demo,
        vendor="Völlig Unbekannte UG",
        description="Sonstige Dienstleistung",
        amount_gross="42.00",
    )
    assert result["category"] == "Unkategorisiert"
    assert result["confidence"] == "fallback"


async def test_categorize_matches_on_description_alone(server_demo: FastMCP) -> None:
    # No vendor given; the description must be enough to match.
    result = await _call_categorize(
        server_demo, description="Tanken bei der Tankstelle", amount_gross="65.00"
    )
    assert result["category"] == "Fahrzeugkosten"


async def test_categorize_empty_input_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="non-empty string"):
        await _call_categorize(server_demo, description="   ", amount_gross="10.00")


async def test_categorize_invalid_amount_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="decimal string"):
        await _call_categorize(server_demo, description="METRO", amount_gross="not-a-number")


async def test_categorize_echoes_input_in_response(server_demo: FastMCP) -> None:
    result = await _call_categorize(
        server_demo,
        vendor="METRO Cash & Carry",
        description="Großhandel",
        amount_gross="123.45",
    )
    assert result["vendor"] == "METRO Cash & Carry"
    assert result["description"] == "Großhandel"
    assert result["amount_gross"] == "123.45"


async def test_categorize_production_raises_clear_error(server_prod: FastMCP) -> None:
    with pytest.raises(ToolError, match="not yet wired"):
        await _call_categorize(server_prod, vendor="METRO", description="x", amount_gross="1.00")
