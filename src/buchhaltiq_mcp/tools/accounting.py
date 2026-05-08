"""Account-resolution MCP tool — the full Kontierung wrapper.

This is the heaviest of the tax-side tools and the one that exposes
the most of the backend's accounting pipeline: given a BuchhaltIQ
category, a tax rate, a payment method and a chart of accounts, it
returns the complete booking pair (account, contra_account, BU-key,
debit/credit side) plus a Decimal-precise net / tax split.

Mirrors AccountResolutionService.resolve() and the
POST /api/accounting/resolve endpoint.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp._money import parse_decimal, parse_tax_rate, round_money, split_gross
from buchhaltiq_mcp.client import BuchhaltIQClient
from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import NotFoundError
from buchhaltiq_mcp.fixtures import load_categories, load_datev_accounts
from buchhaltiq_mcp.models import AccountingCategory, DatevAccount

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


_VALID_SKRS = ("SKR03", "SKR04")
_VALID_PAYMENT_METHODS = ("bank", "cash")

# (rate, side) -> (bu_key, description) — same source of truth as vat.py.
_BU_KEY_TABLE: dict[tuple[Decimal, str], tuple[int, str]] = {
    (Decimal("0"), "expense"): (40, "Steuerfrei / keine Vorsteuer (Aufwand)"),
    (Decimal("0"), "revenue"): (40, "Steuerfrei / keine USt (Erlös)"),
    (Decimal("7"), "expense"): (8, "7% Vorsteuer (ermäßigt, Aufwand)"),
    (Decimal("7"), "revenue"): (2, "7% Umsatzsteuer (ermäßigt, Erlös)"),
    (Decimal("19"), "expense"): (9, "19% Vorsteuer (Regelsatz, Aufwand)"),
    (Decimal("19"), "revenue"): (3, "19% Umsatzsteuer (Regelsatz, Erlös)"),
}

# payment_method, skr -> contra-account number.
_PAYMENT_TO_CONTRA: dict[tuple[str, str], str] = {
    ("bank", "SKR03"): "1200",
    ("bank", "SKR04"): "1800",
    ("cash", "SKR03"): "1000",
    ("cash", "SKR04"): "1600",
}


def _find_category(category_id: str) -> AccountingCategory:
    for cat in load_categories():
        if cat.category_id == category_id:
            return cat
    raise NotFoundError(f"category_id {category_id!r} is not in the BuchhaltIQ category table.")


def _find_account(skr: str, account: str) -> DatevAccount | None:
    for entry in load_datev_accounts():
        if entry.skr == skr and entry.account == account:
            return entry
    return None


def _flatten_validation_messages(items: list[dict[str, Any]]) -> list[str]:
    flattened: list[str] = []
    for item in items:
        msg = item.get("message")
        code = item.get("code")
        if msg and code:
            flattened.append(f"[{code}] {msg}")
        elif msg:
            flattened.append(str(msg))
    return flattened


def register(server: FastMCP, config: Config) -> None:
    """Register the accounting-resolve tool onto ``server``."""
    client = BuchhaltIQClient(config) if config.mode is Mode.PRODUCTION else None

    @server.tool()
    async def resolve_account_assignment(
        category_id: str,
        amount_gross: str,
        payment_method: str = "bank",
        tax_rate: str | None = None,
        skr: str = "SKR03",
    ) -> dict[str, Any]:
        """Resolve a BuchhaltIQ category into a complete DATEV booking pair.

        Returns the full Kontierung an export to DATEV needs: the booking
        account, the contra-account (Gegenkonto), the BU-key, the
        debit/credit side, and the Decimal net / tax split. The result
        includes a ``validation`` block that flags whether both accounts
        exist in the SKR reference (the LLM should refuse to post if
        ``validation.is_valid`` is ``False``).

        Args:
            category_id: BuchhaltIQ category. See ``data/categories.json``
                for the demo set (e.g. ``"wareneinkauf_material"``,
                ``"bewirtung_geschaeftsessen"``, ``"miete_pacht"``,
                ``"erloese_19"``).
            amount_gross: Gross amount of the transaction
                (decimal string, e.g. ``"238.45"``).
            payment_method: ``"bank"`` (default) or ``"cash"``. Drives
                the contra-account selection (1200 / 1000 in SKR03,
                1800 / 1600 in SKR04). Creditor postings are out of
                scope for the demo and require master-data.
            tax_rate: VAT rate as percentage points. If omitted, the
                category's ``default_tax_rate`` is used. For tax-free
                categories (Miete, Personal) the effective rate is
                forced to 0 even if a non-zero rate is supplied.
            skr: Chart of accounts. ``"SKR03"`` (default) or ``"SKR04"``.

        Returns:
            A dictionary with ``category_id``, ``category_title``,
            ``side`` (``"expense"`` / ``"revenue"``), ``skr``,
            ``account``, ``account_title``, ``contra_account``,
            ``contra_account_title``, ``debit_account``,
            ``credit_account``, ``bu_key``, ``bu_key_description``,
            ``tax_rate``, ``amount_gross``, ``amount_net``,
            ``tax_amount``, ``payment_method``, ``currency``, and
            ``validation`` (``is_valid`` + ``errors`` list).

        Raises:
            ValueError: For unsupported SKR / payment-method / tax-rate
                or malformed amounts.
            NotFoundError: For unknown ``category_id``.
        """
        normalised_skr = skr.strip().upper().replace(" ", "")
        if normalised_skr not in _VALID_SKRS:
            raise ValueError(f"skr must be one of {', '.join(_VALID_SKRS)}; got {skr!r}.")

        normalised_payment = payment_method.strip().lower()
        if normalised_payment not in _VALID_PAYMENT_METHODS:
            raise ValueError(
                f"payment_method must be one of {', '.join(_VALID_PAYMENT_METHODS)}; "
                f"got {payment_method!r}."
            )

        gross = parse_decimal(amount_gross, field="amount_gross")
        if gross < 0:
            raise ValueError(f"amount_gross must be non-negative; got {gross}.")

        category = _find_category(category_id)

        # Resolve the effective rate: explicit input wins, else category
        # default. Tax-free categories override any non-zero input.
        raw_rate = tax_rate if tax_rate is not None else category.default_tax_rate
        rate = parse_tax_rate(raw_rate)
        if category.is_tax_free and rate != 0:
            rate = Decimal("0")

        bu_key, bu_description = _BU_KEY_TABLE[(rate, category.side)]
        booking_account = (
            category.skr03_account if normalised_skr == "SKR03" else category.skr04_account
        )
        contra_account = _PAYMENT_TO_CONTRA[(normalised_payment, normalised_skr)]

        # Debit / credit assignment: expense debits the expense account,
        # revenue debits the bank/cash and credits the revenue account.
        if category.side == "expense":
            debit_account, credit_account = booking_account, contra_account
        else:
            debit_account, credit_account = contra_account, booking_account

        if config.mode is Mode.DEMO:
            net, tax = split_gross(gross, rate)

            booking_entry = _find_account(normalised_skr, booking_account)
            contra_entry = _find_account(normalised_skr, contra_account)

            errors: list[str] = []
            if booking_entry is None:
                errors.append(
                    f"Booking account {booking_account} not present in {normalised_skr} reference."
                )
            if contra_entry is None:
                errors.append(
                    f"Contra account {contra_account} not present in {normalised_skr} reference."
                )

            return {
                "category_id": category.category_id,
                "category_title": category.title,
                "side": category.side,
                "skr": normalised_skr,
                "account": booking_account,
                "account_title": booking_entry.title if booking_entry else None,
                "contra_account": contra_account,
                "contra_account_title": contra_entry.title if contra_entry else None,
                "debit_account": debit_account,
                "credit_account": credit_account,
                "bu_key": bu_key,
                "bu_key_description": bu_description,
                "tax_rate": str(rate),
                "amount_gross": str(round_money(gross)),
                "amount_net": str(net),
                "tax_amount": str(tax),
                "payment_method": normalised_payment,
                "currency": "EUR",
                "validation": {
                    "is_valid": not errors,
                    "errors": errors,
                },
            }

        # Production mode: delegate to the backend's POST /api/accounting/resolve.
        assert client is not None
        backend = await client.resolve_account_assignment(
            category_id=category.category_id,
            tax_rate=int(rate),
            payment_method=normalised_payment,
            skr=normalised_skr,
            gross_amount=str(round_money(gross)),
        )

        # Map backend response to the demo response shape so callers can
        # rely on the same keys regardless of mode. Fields the backend
        # does not provide (account titles, payment_method echo, currency)
        # are reconstructed from request inputs and the local fixture.
        backend_account = backend.get("account", booking_account)
        backend_contra = backend.get("contra_account", contra_account)
        debit_credit = backend.get("debit_credit", "S")
        if debit_credit == "S":
            debit, credit = backend_account, backend_contra
        else:
            debit, credit = backend_contra, backend_account

        booking_entry = _find_account(normalised_skr, backend_account)
        contra_entry = _find_account(normalised_skr, backend_contra)
        backend_validation = backend.get("validation") or {}

        return {
            "category_id": backend.get("category_id", category.category_id),
            "category_title": backend.get("category_display", category.title),
            "side": category.side,
            "skr": backend.get("skr", normalised_skr),
            "account": backend_account,
            "account_title": booking_entry.title if booking_entry else None,
            "contra_account": backend_contra,
            "contra_account_title": contra_entry.title if contra_entry else None,
            "debit_account": debit,
            "credit_account": credit,
            "bu_key": int(backend.get("bu_key", bu_key)),
            "bu_key_description": bu_description,
            "tax_rate": str(backend.get("tax_rate", rate)),
            "amount_gross": backend.get("gross_amount") or str(round_money(gross)),
            "amount_net": backend.get("net_amount") or str(_default_split(gross, rate)[0]),
            "tax_amount": backend.get("tax_amount") or str(_default_split(gross, rate)[1]),
            "payment_method": normalised_payment,
            "currency": "EUR",
            "validation": {
                "is_valid": bool(backend_validation.get("is_valid", True)),
                "errors": _flatten_validation_messages(backend_validation.get("errors") or []),
                "warnings": _flatten_validation_messages(backend_validation.get("warnings") or []),
            },
            "posting_class": backend.get("posting_class"),
            "bwa_relevant": backend.get("bwa_relevant"),
        }


def _default_split(gross: Decimal, rate: Decimal) -> tuple[str, str]:
    net, tax = split_gross(gross, rate)
    return str(net), str(tax)
