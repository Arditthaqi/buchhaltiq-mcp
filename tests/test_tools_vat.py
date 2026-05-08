"""Tests for the VAT helper tools.

The expected values are the outputs of the backend's existing
calculate_amounts logic (Decimal split with ROUND_HALF_UP at two
places). If you change the rounding policy, update both this file
and the corresponding backend service in lockstep.
"""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import vat as vat_tool


async def _call(server: FastMCP, name: str, **kwargs: object) -> dict:
    """Invoke a registered VAT tool and unwrap the payload."""
    result = await server.call_tool(name, kwargs)
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
    vat_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    vat_tool.register(server, production_config)
    return server


# ---- extract_vat_from_receipt ------------------------------------------------


@pytest.mark.parametrize(
    ("gross", "rate", "expected_net", "expected_tax"),
    [
        # 19% standard rate examples
        ("238.45", "19", "200.38", "38.07"),
        ("119.00", "19", "100.00", "19.00"),
        ("1000.00", "19", "840.34", "159.66"),
        # 7% reduced rate examples
        ("107.00", "7", "100.00", "7.00"),
        ("12.30", "7", "11.50", "0.80"),
        # 0% / tax-free
        ("500.00", "0", "500.00", "0.00"),
        # Synonym: 0.19 means 19%
        ("119.00", "0.19", "100.00", "19.00"),
    ],
)
async def test_extract_vat_splits_gross_correctly(
    server_demo: FastMCP,
    gross: str,
    rate: str,
    expected_net: str,
    expected_tax: str,
) -> None:
    result = await _call(server_demo, "extract_vat_from_receipt", amount_gross=gross, tax_rate=rate)
    assert result["amount_net"] == expected_net
    assert result["tax_amount"] == expected_tax
    assert result["currency"] == "EUR"


async def test_extract_vat_unsupported_rate_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="not supported"):
        await _call(server_demo, "extract_vat_from_receipt", amount_gross="100.00", tax_rate="16")


async def test_extract_vat_negative_gross_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="non-negative"):
        await _call(server_demo, "extract_vat_from_receipt", amount_gross="-10.00", tax_rate="19")


async def test_extract_vat_invalid_amount_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="decimal string"):
        await _call(server_demo, "extract_vat_from_receipt", amount_gross="abc", tax_rate="19")


async def test_extract_vat_production_raises_clear_error(server_prod: FastMCP) -> None:
    with pytest.raises(ToolError, match="not yet wired"):
        await _call(server_prod, "extract_vat_from_receipt", amount_gross="119.00", tax_rate="19")


# ---- map_tax_rate_to_bu_key --------------------------------------------------


@pytest.mark.parametrize(
    ("rate", "is_expense", "expected_bu", "expected_vorsteuer"),
    [
        ("19", True, 9, True),
        ("19", False, 3, False),
        ("7", True, 8, True),
        ("7", False, 2, False),
        ("0", True, 40, False),
        ("0", False, 40, False),
        ("0.19", True, 9, True),  # synonym for 19
    ],
)
async def test_map_tax_rate_returns_correct_bu_key(
    server_demo: FastMCP,
    rate: str,
    is_expense: bool,
    expected_bu: int,
    expected_vorsteuer: bool,
) -> None:
    result = await _call(
        server_demo, "map_tax_rate_to_bu_key", tax_rate=rate, is_expense=is_expense
    )
    assert result["bu_key"] == expected_bu
    assert result["is_vorsteuer"] is expected_vorsteuer
    assert result["side"] == ("expense" if is_expense else "revenue")


async def test_map_tax_rate_default_side_is_expense(server_demo: FastMCP) -> None:
    result = await _call(server_demo, "map_tax_rate_to_bu_key", tax_rate="19")
    assert result["bu_key"] == 9  # Vorsteuer 19%, the expense side
    assert result["side"] == "expense"


async def test_map_tax_rate_unsupported_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="not supported"):
        await _call(server_demo, "map_tax_rate_to_bu_key", tax_rate="16")
