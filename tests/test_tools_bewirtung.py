"""Tests for the apply_bewirtung_rule tool."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import bewirtung as bewirtung_tool


async def _call(server: FastMCP, **kwargs: object) -> dict:
    """Invoke apply_bewirtung_rule and unwrap the payload."""
    result = await server.call_tool("apply_bewirtung_rule", kwargs)
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
    bewirtung_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    bewirtung_tool.register(server, production_config)
    return server


async def test_geschaeftsessen_119_eur_with_19_pct_vat(server_demo: FastMCP) -> None:
    # Net 100, of which 70 deductible, 30 not. VAT 19 fully recoverable.
    result = await _call(server_demo, amount_gross="119.00", tax_rate="19")
    assert result["amount_net"] == "100.00"
    assert result["tax_amount"] == "19.00"
    assert result["deductible_pct"] == 70
    assert result["net_deductible"] == "70.00"
    assert result["net_non_deductible"] == "30.00"
    assert result["vat_recoverable"] == "19.00"
    assert result["rule"] == "Geschäftsessen 70%"


async def test_mitarbeiterbewirtung_is_fully_deductible(server_demo: FastMCP) -> None:
    result = await _call(server_demo, amount_gross="119.00", tax_rate="19", is_employee_event=True)
    assert result["deductible_pct"] == 100
    assert result["net_deductible"] == "100.00"
    assert result["net_non_deductible"] == "0.00"
    assert result["vat_recoverable"] == "19.00"
    assert result["rule"] == "Mitarbeiterbewirtung 100%"


async def test_default_tax_rate_is_19(server_demo: FastMCP) -> None:
    result = await _call(server_demo, amount_gross="119.00")
    assert result["tax_rate"] == "19"
    assert result["amount_net"] == "100.00"


async def test_geschaeftsessen_with_realistic_restaurant_amount(
    server_demo: FastMCP,
) -> None:
    # 238.45 € restaurant bill, 19% VAT
    result = await _call(server_demo, amount_gross="238.45", tax_rate="19")
    assert result["amount_net"] == "200.38"
    assert result["tax_amount"] == "38.07"
    # 70% of 200.38 = 140.266, rounded to 140.27
    assert result["net_deductible"] == "140.27"
    # 200.38 - 140.27 = 60.11
    assert result["net_non_deductible"] == "60.11"
    # VAT fully recoverable
    assert result["vat_recoverable"] == "38.07"


async def test_zero_tax_rate_means_no_vat_recovery(server_demo: FastMCP) -> None:
    result = await _call(server_demo, amount_gross="100.00", tax_rate="0")
    assert result["tax_amount"] == "0.00"
    assert result["vat_recoverable"] == "0.00"
    assert result["amount_net"] == "100.00"
    assert result["net_deductible"] == "70.00"


async def test_negative_amount_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="non-negative"):
        await _call(server_demo, amount_gross="-50.00", tax_rate="19")


async def test_unsupported_rate_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="not supported"):
        await _call(server_demo, amount_gross="100.00", tax_rate="16")


async def test_production_raises_clear_error(server_prod: FastMCP) -> None:
    with pytest.raises(ToolError, match="not yet wired"):
        await _call(server_prod, amount_gross="119.00", tax_rate="19")
