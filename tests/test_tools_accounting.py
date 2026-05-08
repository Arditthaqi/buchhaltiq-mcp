"""Tests for the resolve_account_assignment tool.

Expected booking pairs are derived from data/categories.json
combined with data/datev_accounts.json. If the fixtures change,
these expectations must change too.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import accounting as accounting_tool


async def _call(server: FastMCP, **kwargs: object) -> dict:
    """Invoke resolve_account_assignment and unwrap the payload."""
    result = await server.call_tool("resolve_account_assignment", kwargs)
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
    accounting_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    accounting_tool.register(server, production_config)
    return server


# ---- happy paths ------------------------------------------------------------


async def test_wareneinkauf_skr03_bank(server_demo: FastMCP) -> None:
    # 238.45 € METRO purchase, 19% VAT, paid by bank.
    result = await _call(
        server_demo,
        category_id="wareneinkauf_material",
        amount_gross="238.45",
        payment_method="bank",
        skr="SKR03",
    )
    assert result["account"] == "3400"
    assert result["contra_account"] == "1200"
    assert result["debit_account"] == "3400"  # expense → debit booking
    assert result["credit_account"] == "1200"
    assert result["bu_key"] == 9
    assert result["amount_net"] == "200.38"
    assert result["tax_amount"] == "38.07"
    assert result["validation"]["is_valid"] is True
    assert result["validation"]["errors"] == []


async def test_wareneinkauf_skr04_bank(server_demo: FastMCP) -> None:
    # Same purchase mapped through SKR04: 5400 booking, 1800 contra.
    result = await _call(
        server_demo,
        category_id="wareneinkauf_material",
        amount_gross="238.45",
        payment_method="bank",
        skr="SKR04",
    )
    assert result["account"] == "5400"
    assert result["contra_account"] == "1800"
    assert result["bu_key"] == 9


async def test_cash_payment_uses_kasse_contra(server_demo: FastMCP) -> None:
    result = await _call(
        server_demo,
        category_id="wareneinkauf_material",
        amount_gross="11.90",
        payment_method="cash",
        skr="SKR03",
    )
    assert result["contra_account"] == "1000"  # SKR03 Kasse


async def test_revenue_side_flips_debit_credit(server_demo: FastMCP) -> None:
    # 19% Erlös: debit bank, credit 8400.
    result = await _call(
        server_demo,
        category_id="erloese_19",
        amount_gross="119.00",
        payment_method="bank",
        skr="SKR03",
    )
    assert result["side"] == "revenue"
    assert result["account"] == "8400"
    assert result["debit_account"] == "1200"  # bank gets debited on revenue
    assert result["credit_account"] == "8400"
    assert result["bu_key"] == 3  # 19% Umsatzsteuer (sales-side)


async def test_tax_free_category_forces_zero_rate(server_demo: FastMCP) -> None:
    # Miete is tax-free per category. Even if the user passes 19, we
    # force it to 0 — protects against a confused LLM accidentally
    # adding VAT to a Miete posting.
    result = await _call(
        server_demo,
        category_id="miete_pacht",
        amount_gross="850.00",
        tax_rate="19",
        skr="SKR03",
    )
    assert result["tax_rate"] == "0"
    assert result["tax_amount"] == "0.00"
    assert result["amount_net"] == "850.00"
    assert result["bu_key"] == 40


async def test_default_tax_rate_picks_category_default(server_demo: FastMCP) -> None:
    # erloese_7 has default_tax_rate "7" — leaving it out should still produce 7.
    result = await _call(
        server_demo,
        category_id="erloese_7",
        amount_gross="107.00",
        skr="SKR03",
    )
    assert result["tax_rate"] == "7"
    assert result["bu_key"] == 2


async def test_account_titles_are_resolved(server_demo: FastMCP) -> None:
    result = await _call(
        server_demo,
        category_id="wareneinkauf_material",
        amount_gross="100.00",
        skr="SKR03",
    )
    assert result["account_title"] == "Wareneingang 19% Vorsteuer"
    assert result["contra_account_title"] == "Bank"


# ---- validation errors ------------------------------------------------------


async def test_unknown_category_raises_not_found(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="not in the BuchhaltIQ category"):
        await _call(
            server_demo,
            category_id="nicht_existent",
            amount_gross="100.00",
        )


async def test_invalid_skr_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="skr must be one of"):
        await _call(
            server_demo,
            category_id="wareneinkauf_material",
            amount_gross="100.00",
            skr="SKR05",
        )


async def test_invalid_payment_method_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="payment_method must be"):
        await _call(
            server_demo,
            category_id="wareneinkauf_material",
            amount_gross="100.00",
            payment_method="bitcoin",
        )


async def test_negative_amount_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="non-negative"):
        await _call(
            server_demo,
            category_id="wareneinkauf_material",
            amount_gross="-50.00",
        )


async def test_unsupported_tax_rate_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="not supported"):
        await _call(
            server_demo,
            category_id="wareneinkauf_material",
            amount_gross="100.00",
            tax_rate="16",
        )


@respx.mock
async def test_production_calls_backend_and_maps_to_demo_shape(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/accounting/resolve"
    respx.post(backend_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "account": "3400",
                "contra_account": "1200",
                "bu_key": "9",
                "debit_credit": "S",
                "tax_rate": 19,
                "net_amount": "200.38",
                "tax_amount": "38.07",
                "gross_amount": "238.45",
                "posting_class": "pnl",
                "bwa_relevant": True,
                "include_in_extf": True,
                "skr": "SKR03",
                "category_id": "wareneinkauf_material",
                "category_display": "Wareneinkauf Material",
                "resolution_source": "category_definitions",
                "validation": {
                    "is_valid": True,
                    "errors": [],
                    "warnings": [],
                    "infos": [],
                    "datev_references": [],
                },
            },
        )
    )

    result = await _call(
        server_prod,
        category_id="wareneinkauf_material",
        amount_gross="238.45",
        payment_method="bank",
        skr="SKR03",
    )

    # Backend payload mapped to MCP-shape keys.
    assert result["account"] == "3400"
    assert result["contra_account"] == "1200"
    assert result["bu_key"] == 9  # cast str→int
    assert result["debit_account"] == "3400"  # debit_credit "S" → account is debit
    assert result["credit_account"] == "1200"
    assert result["amount_net"] == "200.38"
    assert result["tax_amount"] == "38.07"
    assert result["amount_gross"] == "238.45"
    assert result["category_title"] == "Wareneinkauf Material"
    assert result["payment_method"] == "bank"  # echoed from request
    # Account titles come from local fixture (backend does not provide).
    assert result["account_title"] == "Wareneingang 19% Vorsteuer"
    assert result["contra_account_title"] == "Bank"
    assert result["validation"]["is_valid"] is True


@respx.mock
async def test_production_empty_backend_bu_key_uses_local_fallback(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/accounting/resolve"
    respx.post(backend_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "account": "3400",
                "contra_account": "1200",
                "bu_key": "",
                "debit_credit": "S",
                "tax_rate": 19,
                "net_amount": "100.00",
                "tax_amount": "19.00",
                "gross_amount": "119.00",
                "skr": "SKR03",
                "category_id": "wareneinkauf_material",
                "category_display": "Wareneinkauf Material",
                "validation": {"is_valid": True, "errors": [], "warnings": [], "infos": []},
            },
        )
    )

    result = await _call(
        server_prod,
        category_id="wareneinkauf_material",
        amount_gross="119.00",
        payment_method="bank",
        skr="SKR03",
    )

    assert result["bu_key"] == 9


@respx.mock
async def test_production_revenue_side_flips_debit_credit(
    server_prod: FastMCP, production_config: Config
) -> None:
    # Backend says debit_credit="H" → contra is on debit side.
    backend_url = f"{production_config.api_base_url}/api/accounting/resolve"
    respx.post(backend_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "account": "8400",
                "contra_account": "1200",
                "bu_key": "3",
                "debit_credit": "H",
                "tax_rate": 19,
                "net_amount": "100.00",
                "tax_amount": "19.00",
                "gross_amount": "119.00",
                "skr": "SKR03",
                "category_id": "erloese_19",
                "category_display": "Erlöse 19% USt",
                "validation": {"is_valid": True, "errors": [], "warnings": [], "infos": []},
            },
        )
    )

    result = await _call(
        server_prod,
        category_id="erloese_19",
        amount_gross="119.00",
        payment_method="bank",
        skr="SKR03",
    )
    assert result["debit_account"] == "1200"  # bank debited on revenue
    assert result["credit_account"] == "8400"
    assert result["bu_key"] == 3


@respx.mock
async def test_production_propagates_backend_400_as_tool_error(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/accounting/resolve"
    respx.post(backend_url).mock(
        return_value=httpx.Response(400, json={"detail": "Unknown category_id"})
    )

    with pytest.raises(ToolError, match="400"):
        await _call(
            server_prod,
            category_id="wareneinkauf_material",
            amount_gross="119.00",
        )
