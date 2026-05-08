"""Invoice-related MCP tools."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import ProductionNotImplementedError
from buchhaltiq_mcp.fixtures import load_invoices
from buchhaltiq_mcp.models import Invoice, InvoiceStatus

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


def _filter_demo_invoices(
    *,
    status: InvoiceStatus | None,
    customer_id: str | None,
    issued_from: date | None,
    issued_to: date | None,
) -> list[Invoice]:
    invoices = load_invoices()
    if status is not None:
        invoices = [inv for inv in invoices if inv.status is status]
    if customer_id is not None:
        invoices = [inv for inv in invoices if inv.customer_id == customer_id]
    if issued_from is not None:
        invoices = [inv for inv in invoices if inv.issue_date >= issued_from]
    if issued_to is not None:
        invoices = [inv for inv in invoices if inv.issue_date <= issued_to]
    return invoices


def register(server: FastMCP, config: Config) -> None:
    """Register the invoice tools onto ``server``."""

    @server.tool()
    async def list_invoices(
        status: InvoiceStatus | None = None,
        customer_id: str | None = None,
        issued_from: date | None = None,
        issued_to: date | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List BuchhaltIQ invoices with optional filters.

        Args:
            status: Restrict to invoices in this lifecycle state
                (``draft``, ``open``, ``paid``, ``overdue``, ``cancelled``).
            customer_id: Restrict to invoices for a single customer.
            issued_from: Inclusive lower bound on the issue date (ISO 8601).
            issued_to: Inclusive upper bound on the issue date (ISO 8601).
            limit: Maximum number of invoices to return (default 50, max 200).

        Returns:
            A list of invoice dictionaries, newest first by issue date.
        """
        capped_limit = max(1, min(limit, 200))

        if config.mode is Mode.DEMO:
            invoices = _filter_demo_invoices(
                status=status,
                customer_id=customer_id,
                issued_from=issued_from,
                issued_to=issued_to,
            )
            invoices.sort(key=lambda inv: inv.issue_date, reverse=True)
            return [inv.model_dump(mode="json") for inv in invoices[:capped_limit]]

        raise ProductionNotImplementedError(
            "list_invoices is not yet wired to the production BuchhaltIQ API. "
            "Set BUCHHALTIQ_MCP_MODE=demo to use fixture data."
        )
