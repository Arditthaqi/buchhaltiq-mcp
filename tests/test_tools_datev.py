"""Tests for the validate_datev_account tool."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import datev as datev_tool


async def _call(server: FastMCP, name: str, **kwargs: object) -> dict:
    """Invoke a registered DATEV tool and unwrap the payload."""
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
    datev_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    datev_tool.register(server, production_config)
    return server


@pytest.mark.parametrize(
    ("skr", "account", "expected_title_fragment"),
    [
        ("SKR03", "1000", "Kasse"),
        ("SKR03", "1576", "Vorsteuer 19%"),
        ("SKR03", "4650", "Bewirtung"),
        ("SKR04", "1800", "Bank"),
        ("SKR04", "5400", "Wareneingang"),
        ("SKR04", "6650", "Bewirtung"),
    ],
)
async def test_validate_known_account_returns_valid(
    server_demo: FastMCP,
    skr: str,
    account: str,
    expected_title_fragment: str,
) -> None:
    result = await _call(server_demo, "validate_datev_account", skr=skr, account=account)
    assert result["is_valid"] is True
    assert result["skr"] == skr
    assert result["account"] == account
    assert expected_title_fragment in result["title"]
    assert result["errors"] == []


async def test_validate_unknown_account_returns_invalid_with_suggestions(
    server_demo: FastMCP,
) -> None:
    result = await _call(server_demo, "validate_datev_account", skr="SKR03", account="1577")
    assert result["is_valid"] is False
    assert any("not present" in err for err in result["errors"])
    # 1576 (Vorsteuer 19%) and 1571 (Vorsteuer 7%) share a 3-digit prefix
    # with 1577 — at least one of them should appear as a suggestion.
    suggestion_accounts = {s["account"] for s in result["suggestions"]}
    assert suggestion_accounts & {"1576", "1571"}


async def test_validate_skr_is_normalised(server_demo: FastMCP) -> None:
    result = await _call(server_demo, "validate_datev_account", skr=" skr03 ", account="1000")
    assert result["is_valid"] is True
    assert result["skr"] == "SKR03"


async def test_validate_unknown_skr_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="must be one of"):
        await _call(server_demo, "validate_datev_account", skr="SKR05", account="1000")


async def test_validate_empty_account_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="non-empty"):
        await _call(server_demo, "validate_datev_account", skr="SKR03", account="   ")


async def test_validate_production_raises_clear_error(server_prod: FastMCP) -> None:
    with pytest.raises(ToolError, match="not yet wired"):
        await _call(server_prod, "validate_datev_account", skr="SKR03", account="1000")
