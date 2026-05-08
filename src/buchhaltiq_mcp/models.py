"""Pydantic models for the BuchhaltIQ domain.

Kept intentionally small — the demo fixtures are realistic but not exhaustive.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class InvoiceStatus(StrEnum):
    """Lifecycle status of an invoice."""

    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class Customer(BaseModel):
    """A BuchhaltIQ customer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    contact_email: str | None = None
    city: str | None = None
    country: str = "DE"


class Invoice(BaseModel):
    """A BuchhaltIQ invoice."""

    model_config = ConfigDict(extra="forbid")

    id: str
    customer_id: str
    issue_date: date
    due_date: date
    status: InvoiceStatus
    total_net: Decimal
    total_gross: Decimal
    currency: str = "EUR"
    description: str | None = None


class Beleg(BaseModel):
    """A BuchhaltIQ receipt / supporting document."""

    model_config = ConfigDict(extra="forbid")

    id: str
    issue_date: date
    vendor: str
    amount_gross: Decimal
    category: str | None = None
    description: str = Field(default="", description="Free-text from the receipt")


class MonthlyReport(BaseModel):
    """A BWA-style monthly profit-and-loss summary."""

    model_config = ConfigDict(extra="forbid")

    year: int
    month: int = Field(ge=1, le=12)
    revenue_total: Decimal
    expense_total: Decimal
    profit: Decimal
    currency: str = "EUR"
    invoice_count: int
    beleg_count: int


class DatevAccount(BaseModel):
    """A single account in a DATEV chart of accounts (SKR03 or SKR04)."""

    model_config = ConfigDict(extra="forbid")

    skr: str
    account: str
    title: str
    type: str
