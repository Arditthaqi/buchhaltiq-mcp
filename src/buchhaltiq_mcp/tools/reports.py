"""Reporting MCP tools (monthly P&L summary)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.client import BuchhaltIQClient
from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.fixtures import load_belege, load_invoices, load_month_overviews
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


def _validate_period_key(period_key: str) -> tuple[int, int]:
    value = (period_key or "").strip()
    parts = value.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        raise ValueError("period_key must use YYYY-MM format.")
    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError as exc:
        raise ValueError("period_key must use YYYY-MM format.") from exc
    if not (2000 <= year <= 2100) or not (1 <= month <= 12):
        raise ValueError("period_key must use YYYY-MM format.")
    return year, month


def _empty_demo_month_overview(period_key: str, year: int, month: int) -> dict[str, Any]:
    return {
        "period_key": period_key,
        "year": year,
        "month": month,
        "currency": "EUR",
        "income": {
            "total": "0.00",
            "pos_revenue": "0.00",
            "invoice_revenue": "0.00",
            "standalone_income": "0.00",
            "daily_report_count": 0,
            "invoice_payment_count": 0,
            "standalone_income_count": 0,
            "excluded_linked_income_count": 0,
            "excluded_operational_bank_income_count": 0,
            "pos_payment_breakdown": {
                "cash": "0.00",
                "card": "0.00",
                "transfer": "0.00",
                "invoice": "0.00",
            },
        },
        "expenses": {
            "gross_expenses": "0.00",
            "refunds": "0.00",
            "net_expenses": "0.00",
            "transaction_count": 0,
            "refund_count": 0,
            "excluded_count": 0,
            "excluded_total": "0.00",
            "by_category": [],
        },
        "profit": "0.00",
        "vat": {
            "output_tax": "0.00",
            "input_tax": "0.00",
            "net_vat_due_estimate": "0.00",
            "by_rate": [],
            "basis": "demo fixture",
        },
        "readiness": {
            "missing_receipt_count": 0,
            "uncategorized_transaction_count": 0,
            "receipt_count": 0,
            "month_locked": False,
            "datev_export_status": None,
            "can_prepare_datev": True,
        },
        "source_counts": {
            "bank_transactions": 0,
            "daily_reports": 0,
            "invoice_payments": 0,
            "receipts": 0,
        },
        "warnings": ["No demo accounting data exists for this period."],
        "methodology": [
            "POS revenue is read from dailyReports.totalRevenue.",
            "Invoice revenue is read from invoice payments by paidAt and excludes origin=pos.",
            "Standalone income uses exportable P&L income categories such as sonstige_einnahmen.",
            "Expenses use P&L expense categories; neutral, tax, private, clearing and "
            "balance-sheet items are excluded.",
        ],
    }


def _build_demo_accounting_month_overview(period_key: str) -> dict[str, Any]:
    year, month = _validate_period_key(period_key)
    for overview in load_month_overviews():
        if overview.get("period_key") == period_key:
            return overview
    return _empty_demo_month_overview(period_key, year, month)


def register(server: FastMCP, config: Config) -> None:
    """Register the reporting tools onto ``server``."""
    client = BuchhaltIQClient(config) if config.mode is Mode.PRODUCTION else None

    @server.tool()
    async def monthly_report(year: int, month: int) -> dict[str, Any]:
        """Build a BWA-style monthly profit-and-loss summary.

        Production mode: the backend computes the numbers with the same
        BuchhaltIQ accounting month overview as ``accounting_month_overview``,
        the month report and the app (one result, by cash flow). Revenue is
        POS revenue from daily reports plus invoice payments of the month
        (credit-note payments subtracted, ``origin=pos`` excluded) plus
        standalone P&L income. Expenses are P&L expenses incl. wages;
        Umsatzsteuer (also prior years) and Gewerbesteuer count by cash flow,
        a refund reduces expenses; Einkommensteuer is private and never
        counts. Profit equals revenue minus expenses. The response also
        carries ``period_key``, ``pos_revenue``, ``standalone_income``,
        ``tax_payments_total``, ``tax_payment_count``, ``result_rule`` and
        ``warnings``.

        Demo mode: revenue is the sum of gross totals of fixture invoices
        issued in the month with status ``paid``, ``open`` or ``overdue``;
        expenses are the gross amounts of fixture receipts dated in the month.

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

        # Production mode: delegate to the backend's aggregation endpoint.
        assert client is not None
        return await client.monthly_report(year=year, month=month)

    @server.tool()
    async def accounting_month_overview(period_key: str) -> dict[str, Any]:
        """Build the BuchhaltIQ accounting month overview from authoritative sources.

        This is the richer successor to ``monthly_report`` for product-aware
        accounting questions. It mirrors BuchhaltIQ's frontend/export logic:
        POS revenue comes from ``dailyReports.totalRevenue``; invoice revenue
        comes from actual payments by ``paidAt`` and excludes ``origin=pos``;
        standalone income is limited to exportable P&L income categories; and
        expenses are grouped by P&L expense category while neutral, private,
        clearing, and balance-sheet movements are excluded. Tax payments
        count by cash flow: Umsatzsteuer (also prior years) and Gewerbesteuer
        payments are expenses, their refunds reduce expenses (listed in
        ``expenses.tax_payments``); Einkommensteuer is private and never
        counts; Koerperschaftsteuer is excluded. ``result_rule`` names the
        rule version.

        Args:
            period_key: Month in ``YYYY-MM`` format.

        Returns:
            A dictionary with income, expenses, VAT, readiness, source counts,
            warnings, and methodology. Money values are decimal strings.

        Raises:
            ValueError: If ``period_key`` is not in ``YYYY-MM`` format.
        """
        _validate_period_key(period_key)

        if config.mode is Mode.DEMO:
            return _build_demo_accounting_month_overview(period_key)

        assert client is not None
        return await client.accounting_month_overview(period_key=period_key)
