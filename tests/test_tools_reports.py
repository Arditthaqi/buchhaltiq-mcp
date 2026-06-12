"""Tests for the monthly_report tool.

Test anchor values are derived from the shipped fixtures (`data/invoices.json`,
`data/belege.json`). If the fixtures change, these expectations must change too.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import reports as reports_tool


async def _call_report_tool(server: FastMCP, name: str, **kwargs: object) -> dict:
    """Invoke a registered reports tool and unwrap the payload."""
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


async def _call_monthly_report(server: FastMCP, **kwargs: object) -> dict:
    return await _call_report_tool(server, "monthly_report", **kwargs)


@pytest.fixture
def server_demo(demo_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    reports_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    reports_tool.register(server, production_config)
    return server


async def test_monthly_report_january_2026_matches_fixture_totals(
    server_demo: FastMCP,
) -> None:
    # inv_2026_0001 paid 1011.50 + inv_2026_0002 paid 499.80; bel_001 METRO 238.45.
    report = await _call_monthly_report(server_demo, year=2026, month=1)
    assert report["year"] == 2026
    assert report["month"] == 1
    assert report["revenue_total"] == "1511.30"
    assert report["expense_total"] == "238.45"
    assert report["profit"] == "1272.85"
    assert report["invoice_count"] == 2
    assert report["beleg_count"] == 1
    assert report["currency"] == "EUR"


async def test_monthly_report_march_2026_matches_fixture_totals(
    server_demo: FastMCP,
) -> None:
    # inv_2026_0005 open 3510.50 + inv_2026_0006 open 809.20;
    # bel_004 Telekom 59.99 + bel_005 OBI 147.80.
    report = await _call_monthly_report(server_demo, year=2026, month=3)
    assert report["revenue_total"] == "4319.70"
    assert report["expense_total"] == "207.79"
    assert report["profit"] == "4111.91"
    assert report["invoice_count"] == 2
    assert report["beleg_count"] == 2


async def test_monthly_report_april_2026_excludes_draft_invoices(
    server_demo: FastMCP,
) -> None:
    # inv_2026_0007 open 606.90 counts; inv_2026_0008 draft 1404.20 must NOT.
    # bel_006 DATEV 89.00.
    report = await _call_monthly_report(server_demo, year=2026, month=4)
    assert report["revenue_total"] == "606.90"
    assert report["expense_total"] == "89.00"
    assert report["profit"] == "517.90"
    assert report["invoice_count"] == 1


async def test_monthly_report_empty_month_returns_zero_totals(
    server_demo: FastMCP,
) -> None:
    report = await _call_monthly_report(server_demo, year=2026, month=5)
    assert report["revenue_total"] == "0.00"
    assert report["expense_total"] == "0.00"
    assert report["profit"] == "0.00"
    assert report["invoice_count"] == 0
    assert report["beleg_count"] == 0


async def test_monthly_report_invalid_month_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="month must be"):
        await _call_monthly_report(server_demo, year=2026, month=13)


async def test_monthly_report_invalid_year_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="year must be"):
        await _call_monthly_report(server_demo, year=1999, month=6)


async def test_accounting_month_overview_april_2026_uses_authoritative_sources(
    server_demo: FastMCP,
) -> None:
    overview = await _call_report_tool(
        server_demo,
        "accounting_month_overview",
        period_key="2026-04",
    )

    assert overview["period_key"] == "2026-04"
    assert overview["income"]["pos_revenue"] == "1000.00"
    assert overview["income"]["invoice_revenue"] == "188.00"
    assert overview["income"]["standalone_income"] == "100.00"
    assert overview["income"]["total"] == "1288.00"
    assert overview["income"]["excluded_linked_income_count"] == 1
    assert overview["income"]["excluded_operational_bank_income_count"] == 1
    assert overview["expenses"]["net_expenses"] == "100.00"
    assert overview["profit"] == "1188.00"
    assert overview["readiness"]["can_prepare_datev"] is False


async def test_accounting_month_overview_empty_demo_month_returns_zero(
    server_demo: FastMCP,
) -> None:
    overview = await _call_report_tool(
        server_demo,
        "accounting_month_overview",
        period_key="2026-05",
    )

    assert overview["income"]["total"] == "0.00"
    assert overview["expenses"]["net_expenses"] == "0.00"
    assert overview["profit"] == "0.00"
    assert overview["warnings"] == ["No demo accounting data exists for this period."]


async def test_accounting_month_overview_invalid_period_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="YYYY-MM"):
        await _call_report_tool(server_demo, "accounting_month_overview", period_key="2026/04")


@respx.mock
async def test_monthly_report_production_passes_through_backend(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/user-invoices/monthly-report"
    respx.get(backend_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "year": 2026,
                "month": 3,
                "revenue_total": "5400.00",
                "expense_total": "1200.50",
                "profit": "4199.50",
                "currency": "EUR",
                "invoice_count": 4,
                "beleg_count": 12,
            },
        )
    )

    report = await _call_monthly_report(server_prod, year=2026, month=3)
    assert report["revenue_total"] == "5400.00"
    assert report["expense_total"] == "1200.50"
    assert report["profit"] == "4199.50"
    assert report["invoice_count"] == 4
    assert report["beleg_count"] == 12


@respx.mock
async def test_accounting_month_overview_production_passes_through_backend(
    server_prod: FastMCP, production_config: Config
) -> None:
    backend_url = f"{production_config.api_base_url}/api/mcp/month-overview/2026-04"
    respx.get(backend_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "period_key": "2026-04",
                "currency": "EUR",
                "income": {"total": "1288.00", "pos_revenue": "1000.00"},
                "expenses": {"net_expenses": "100.00"},
                "profit": "1188.00",
            },
        )
    )

    overview = await _call_report_tool(
        server_prod,
        "accounting_month_overview",
        period_key="2026-04",
    )
    assert overview["income"]["pos_revenue"] == "1000.00"
    assert overview["income"]["total"] == "1288.00"
    assert overview["profit"] == "1188.00"
