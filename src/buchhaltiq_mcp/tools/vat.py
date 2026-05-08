"""VAT (Mehrwertsteuer / Umsatzsteuer) helper tools.

These tools mirror logic that already exists in the BuchhaltIQ backend
(``app/services/receipt_analysis.py``, ``app/services/tax_key_mapper.py``)
and expose it to the LLM in a small, deterministic shape. The demo
implementation reproduces the math and the BU-key table; production
mode will delegate to the backend services so a single source of truth
applies.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import ProductionNotImplementedError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


# Supported German VAT rates as percentage points. 16% (2020 COVID reduction)
# is intentionally not in the demo set — backend handles it for historical
# data, but exposing it via the LLM would invite unintended use.
_SUPPORTED_RATES = (Decimal("0"), Decimal("7"), Decimal("19"))

# DATEV BU-key table as used by the backend's tax_key_mapper.
# Tuple shape: (rate, is_expense) -> (bu_key, description, is_vorsteuer).
_BU_KEY_TABLE: dict[tuple[Decimal, bool], tuple[int, str, bool]] = {
    (Decimal("0"), False): (40, "Steuerfrei / keine USt (Erlös)", False),
    (Decimal("0"), True): (40, "Steuerfrei / keine Vorsteuer (Aufwand)", False),
    (Decimal("7"), False): (2, "7% Umsatzsteuer (ermäßigt, Erlös)", False),
    (Decimal("7"), True): (8, "7% Vorsteuer (ermäßigt, Aufwand)", True),
    (Decimal("19"), False): (3, "19% Umsatzsteuer (Regelsatz, Erlös)", False),
    (Decimal("19"), True): (9, "19% Vorsteuer (Regelsatz, Aufwand)", True),
}

_TWO_PLACES = Decimal("0.01")


def _parse_decimal(raw: str, *, field: str) -> Decimal:
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal string (e.g. '238.45'); got {raw!r}.") from exc


def _parse_tax_rate(raw: str) -> Decimal:
    """Accept '19', '19.0', '0.19' and normalise to percentage points."""
    rate = _parse_decimal(raw, field="tax_rate")
    # Allow '0.19' as a synonym for '19'.
    if rate < 1 and rate > 0:
        rate = rate * Decimal("100")
    if rate not in _SUPPORTED_RATES:
        supported = ", ".join(str(r) for r in _SUPPORTED_RATES)
        raise ValueError(
            f"tax_rate {rate}% is not supported in demo mode "
            f"(supported: {supported}%). The backend handles others; "
            f"keep them out of LLM-driven flows."
        )
    return rate


def _round(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _split_gross(gross: Decimal, rate: Decimal) -> tuple[Decimal, Decimal]:
    """Return (net, tax) given a gross amount and a percentage-point rate."""
    if rate == 0:
        return _round(gross), Decimal("0.00")
    divisor = Decimal("1") + (rate / Decimal("100"))
    net = _round(gross / divisor)
    tax = _round(gross - net)
    return net, tax


def register(server: FastMCP, config: Config) -> None:
    """Register the VAT helper tools onto ``server``."""

    @server.tool()
    async def extract_vat_from_receipt(
        amount_gross: str,
        tax_rate: str,
    ) -> dict[str, Any]:
        """Split a gross amount into net and VAT for a single tax rate.

        Mirrors the backend's ``calculate_amounts`` logic. Uses Decimal
        arithmetic with bankers'-style two-decimal rounding (ROUND_HALF_UP)
        to stay aligned with German invoicing conventions.

        Args:
            amount_gross: Gross amount as a decimal string (e.g. ``"238.45"``).
            tax_rate: VAT rate in percentage points (e.g. ``"19"`` or
                ``"19.0"``). Synonyms ``"0.19"`` are accepted and treated
                as 19%. Supported rates: 0, 7, 19.

        Returns:
            A dictionary with ``amount_gross``, ``amount_net``,
            ``tax_amount``, ``tax_rate`` (normalised), and ``currency``
            (always ``"EUR"``). Money values are decimal strings with
            two-place precision.

        Raises:
            ValueError: If ``amount_gross`` is not a valid decimal,
                ``tax_rate`` is not parseable, or the rate is unsupported.
        """
        gross = _parse_decimal(amount_gross, field="amount_gross")
        if gross < 0:
            raise ValueError(
                f"amount_gross must be non-negative; got {gross}. "
                "Refunds and storno are out of scope for this tool."
            )

        rate = _parse_tax_rate(tax_rate)

        if config.mode is Mode.DEMO:
            net, tax = _split_gross(gross, rate)
            return {
                "amount_gross": str(_round(gross)),
                "amount_net": str(net),
                "tax_amount": str(tax),
                "tax_rate": str(rate),
                "currency": "EUR",
            }

        raise ProductionNotImplementedError(
            "extract_vat_from_receipt is not yet wired to the production "
            "BuchhaltIQ API. Set BUCHHALTIQ_MCP_MODE=demo to use the "
            "in-process implementation."
        )

    @server.tool()
    async def map_tax_rate_to_bu_key(
        tax_rate: str,
        is_expense: bool = True,
    ) -> dict[str, Any]:
        """Look up the DATEV BU-key for a German VAT rate.

        Mirrors the BU-key table used by the backend's ``TaxKeyMapper``:
        2 / 3 for sales-side VAT (Umsatzsteuer), 8 / 9 for purchase-side
        input tax (Vorsteuer), 40 for tax-free posts. ``is_expense`` is
        the side flag — ``True`` (default) means a Vorsteuer / Aufwand
        booking, ``False`` means an Umsatzsteuer / Erlös booking.

        Args:
            tax_rate: VAT rate in percentage points (``"0"``, ``"7"``,
                ``"19"``). ``"0.19"`` is accepted as 19%.
            is_expense: ``True`` (default) for purchase-side bookings
                (Vorsteuer / Aufwand). ``False`` for sales-side
                bookings (Umsatzsteuer / Erlös).

        Returns:
            A dictionary with ``bu_key`` (int), ``description``,
            ``is_vorsteuer`` (bool), ``tax_rate``, and ``side``
            (``"expense"`` or ``"revenue"``).

        Raises:
            ValueError: If the rate is unsupported.
        """
        rate = _parse_tax_rate(tax_rate)
        bu_key, description, is_vorsteuer = _BU_KEY_TABLE[(rate, is_expense)]
        return {
            "bu_key": bu_key,
            "description": description,
            "is_vorsteuer": is_vorsteuer,
            "tax_rate": str(rate),
            "side": "expense" if is_expense else "revenue",
        }
