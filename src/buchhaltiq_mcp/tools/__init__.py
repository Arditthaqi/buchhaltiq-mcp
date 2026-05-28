"""MCP tool implementations.

Tools live in dedicated modules per domain (invoices, customers, …) and are
registered into a :class:`mcp.server.fastmcp.FastMCP` instance via
:func:`register_all`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from buchhaltiq_mcp.tools import (
    accounting,
    belege,
    bewirtung,
    categorize,
    customers,
    datev,
    hr,
    invoices,
    reports,
    split,
    vat,
)

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
    vat.register(server, config)
    datev.register(server, config)
    bewirtung.register(server, config)
    split.register(server, config)
    accounting.register(server, config)
    hr.register(server, config)
