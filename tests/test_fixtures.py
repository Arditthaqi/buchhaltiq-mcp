"""Tests for the fixture loader."""

from __future__ import annotations

from buchhaltiq_mcp.fixtures import load_belege, load_customers, load_invoices
from buchhaltiq_mcp.models import InvoiceStatus


def test_customers_load_and_validate() -> None:
    customers = load_customers()
    assert len(customers) >= 5
    # Demo data must be obviously demo, not foo/bar — the briefing requires it.
    assert all("Demo" in c.name or c.name.endswith("(Demo)") for c in customers)
    assert all(c.country == "DE" for c in customers)


def test_invoices_reference_known_customers() -> None:
    invoices = load_invoices()
    customer_ids = {c.id for c in load_customers()}
    assert all(inv.customer_id in customer_ids for inv in invoices)


def test_invoices_cover_each_status() -> None:
    statuses = {inv.status for inv in load_invoices()}
    # We want a realistic mix so example workflows are interesting.
    assert {InvoiceStatus.PAID, InvoiceStatus.OPEN, InvoiceStatus.OVERDUE}.issubset(statuses)


def test_belege_load_with_german_categories() -> None:
    belege = load_belege()
    assert len(belege) >= 5
    categories = {b.category for b in belege if b.category}
    # German bookkeeping vocabulary — sanity check that fixtures aren't generic.
    assert any(cat in {"Wareneinkauf", "Fahrzeugkosten", "Telekommunikation"} for cat in categories)
