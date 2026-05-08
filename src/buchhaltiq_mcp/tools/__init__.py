"""MCP tool implementations.

Tools live in dedicated modules per domain (invoices, customers, …) and are
registered into a :class:`mcp.server.fastmcp.FastMCP` instance via
:func:`register_all`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from buchhaltiq_mcp.tools import belege, categorize, customers, invoices, reports

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


def register_all(server: FastMCP, config: Config) -> None:
    """Register every tool module against the given FastMCP server."""
    invoices.register(server, config)
    customers.register(server, config)
    belege.register(server, config)
    reports.register(server, config)
    categorize.register(server, config)
