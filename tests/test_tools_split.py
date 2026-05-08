"""Tests for the split_mixed_tax_receipt tool."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import split as split_tool


async def _call(server: FastMCP, **kwargs: object) -> dict:
    """Invoke split_mixed_tax_receipt and unwrap the payload."""
    result = await server.call_tool("split_mixed_tax_receipt", kwargs)
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
    split_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    split_tool.register(server, production_config)
    return server


async def test_single_rate_does_not_count_as_mixed(server_demo: FastMCP) -> None:
    result = await _call(
        server_demo,
        positions=[
            {"amount_gross": "59.50", "tax_rate": "19", "description": "Werkzeug"},
            {"amount_gross": "59.50", "tax_rate": "19", "description": "Reinigung"},
        ],
    )
    assert result["has_mixed_tax"] is False
    assert result["total_gross"] == "119.00"
    assert result["total_net"] == "100.00"
    assert result["total_tax"] == "19.00"
    assert list(result["breakdown_by_rate"].keys()) == ["19"]


async def test_mixed_7_and_19_supermarket_run(server_demo: FastMCP) -> None:
    # Realistic METRO mixed receipt: groceries 7%, non-food 19%.
    result = await _call(
        server_demo,
        positions=[
            {"amount_gross": "53.50", "tax_rate": "7", "description": "Lebensmittel"},
            {"amount_gross": "23.80", "tax_rate": "19", "description": "Reiniger"},
        ],
    )
    assert result["has_mixed_tax"] is True
    assert result["total_gross"] == "77.30"
    breakdown = result["breakdown_by_rate"]
    # 7% bucket
    assert breakdown["7"]["gross"] == "53.50"
    assert breakdown["7"]["net"] == "50.00"
    assert breakdown["7"]["tax"] == "3.50"
    assert breakdown["7"]["position_count"] == 1
    # 19% bucket
    assert breakdown["19"]["gross"] == "23.80"
    assert breakdown["19"]["net"] == "20.00"
    assert breakdown["19"]["tax"] == "3.80"
    assert breakdown["19"]["position_count"] == 1


async def test_three_rates_with_zero_for_pfand(server_demo: FastMCP) -> None:
    # Pfand is treated as 0% in many supermarket flows.
    result = await _call(
        server_demo,
        positions=[
            {"amount_gross": "10.70", "tax_rate": "7"},
            {"amount_gross": "11.90", "tax_rate": "19"},
            {"amount_gross": "0.50", "tax_rate": "0"},
        ],
    )
    assert result["has_mixed_tax"] is True
    assert set(result["breakdown_by_rate"].keys()) == {"0", "7", "19"}
    assert result["total_gross"] == "23.10"


async def test_expected_total_match_emits_no_warnings(server_demo: FastMCP) -> None:
    result = await _call(
        server_demo,
        positions=[
            {"amount_gross": "53.50", "tax_rate": "7"},
            {"amount_gross": "23.80", "tax_rate": "19"},
        ],
        expected_total_gross="77.30",
    )
    assert result["warnings"] == []


async def test_expected_total_mismatch_emits_warning(server_demo: FastMCP) -> None:
    result = await _call(
        server_demo,
        positions=[
            {"amount_gross": "53.50", "tax_rate": "7"},
            {"amount_gross": "23.80", "tax_rate": "19"},
        ],
        expected_total_gross="80.00",
    )
    assert len(result["warnings"]) == 1
    assert "does not match" in result["warnings"][0]


async def test_empty_positions_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="at least one"):
        await _call(server_demo, positions=[])


async def test_negative_position_amount_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="non-negative"):
        await _call(
            server_demo,
            positions=[{"amount_gross": "-10.00", "tax_rate": "19"}],
        )


async def test_unsupported_rate_in_position_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="not supported"):
        await _call(
            server_demo,
            positions=[{"amount_gross": "100.00", "tax_rate": "16"}],
        )


async def test_production_raises_clear_error(server_prod: FastMCP) -> None:
    with pytest.raises(ToolError, match="not yet wired"):
        await _call(
            server_prod,
            positions=[{"amount_gross": "119.00", "tax_rate": "19"}],
        )
