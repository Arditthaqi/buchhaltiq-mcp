"""Reporting MCP tools (monthly P&L summary)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import ProductionNotImplementedError
from buchhaltiq_mcp.fixtures import load_belege, load_invoices
from buchhaltiq_mcp.models import InvoiceStatus, MonthlyReport

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


# Drafts are not yet billed; cancellations never become revenue.
_REVENUE_STATUSES = frozenset({InvoiceStatus.PAID, InvoiceStatus.OPEN, InvoiceStatus.OVERDUE})
_ZERO = Decimal("0.00")


def _build_demo_monthly_report(year: int, month: int) -> MonthlyReport:
    invoices = [
        inv
        for inv in load_invoices()
        if inv.status in _REVENUE_STATUSES
        and inv.issue_date.year == year
        and inv.issue_date.month == month
    ]
    belege = [b for b in load_belege() if b.issue_date.year == year and b.issue_date.month == month]
    revenue = sum((inv.total_gross for inv in invoices), _ZERO)
    expense = sum((b.amount_gross for b in belege), _ZERO)
    return MonthlyReport(
        year=year,
        month=month,
        revenue_total=revenue,
        expense_total=expense,
        profit=revenue - expense,
        invoice_count=len(invoices),
        beleg_count=len(belege),
    )


def register(server: FastMCP, config: Config) -> None:
    """Register the reporting tools onto ``server``."""

    @server.tool()
    async def monthly_report(year: int, month: int) -> dict[str, Any]:
        """Build a BWA-style monthly profit-and-loss summary.

        Revenue is the sum of gross totals of invoices issued in the month
        with status ``paid``, ``open``, or ``overdue``. Drafts and cancelled
        invoices are excluded — drafts because they are not yet billed,
        cancellations because they never become revenue.

        Expenses are the sum of gross amounts of receipts (``Belege``)
        dated in the month. Profit equals revenue minus expenses.

        Args:
            year: Four-digit calendar year (2000-2100).
            month: Month number (1-12).

        Returns:
            A dictionary with ``year``, ``month``, ``revenue_total``,
            ``expense_total``, ``profit``, ``currency`` (always ``EUR``),
            ``invoice_count``, and ``beleg_count``. Money values are
            serialized as decimal strings to preserve precision.

        Raises:
            ValueError: If ``year`` or ``month`` is outside the supported range.
        """
        if not (2000 <= year <= 2100):
            raise ValueError("year must be between 2000 and 2100.")
        if not (1 <= month <= 12):
            raise ValueError("month must be between 1 and 12.")

        if config.mode is Mode.DEMO:
            report = _build_demo_monthly_report(year, month)
            return report.model_dump(mode="json")

        raise ProductionNotImplementedError(
            "monthly_report is not yet wired to the production BuchhaltIQ API. "
            "Set BUCHHALTIQ_MCP_MODE=demo to use fixture data."
        )
