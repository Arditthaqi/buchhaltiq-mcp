"""Shared Decimal / VAT helpers used across the tax-side tools.

Centralised here so the rounding policy, the supported VAT rates, and
the gross-to-net split formula have a single source of truth. Every
tool that touches money should import from this module rather than
reproducing the math locally.

The leading underscore on the filename signals package-internal use:
nothing here is part of the public MCP-tool surface.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# German invoicing convention: ROUND_HALF_UP at two decimal places.
TWO_PLACES = Decimal("0.01")

# Supported German VAT rates (percentage points). 16% (the 2020 COVID
# reduction) is intentionally excluded — the backend handles it for
# historical data, but we do not surface it to the LLM.
SUPPORTED_RATES = (Decimal("0"), Decimal("7"), Decimal("19"))


def parse_decimal(
    raw: str,
    *,
    field: str,
    position_idx: int | None = None,
) -> Decimal:
    """Parse a decimal-string input field, raising a clear error on failure.

    ``position_idx`` is appended to the error message when the field
    comes from a per-position context (used by ``split_mixed_tax_receipt``).
    """
    where = f" (position {position_idx})" if position_idx is not None else ""
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field}{where} must be a decimal string; got {raw!r}.") from exc


def parse_tax_rate(raw: str, *, position_idx: int | None = None) -> Decimal:
    """Parse a VAT-rate input and normalise to percentage points.

    Accepts both percentage-point form (``"19"``, ``"7"``, ``"0"``) and
    fraction form (``"0.19"``, ``"0.07"``). Rejects rates outside the
    supported set with a message naming the supported values.
    """
    rate = parse_decimal(raw, field="tax_rate", position_idx=position_idx)
    if 0 < rate < 1:
        rate = rate * Decimal("100")
    if rate not in SUPPORTED_RATES:
        supported = ", ".join(str(r) for r in SUPPORTED_RATES)
        where = f" (position {position_idx})" if position_idx is not None else ""
        raise ValueError(f"tax_rate {rate}%{where} is not supported (supported: {supported}%).")
    return rate


def round_money(value: Decimal) -> Decimal:
    """Quantize a Decimal to two places using ROUND_HALF_UP."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def split_gross(gross: Decimal, rate: Decimal) -> tuple[Decimal, Decimal]:
    """Return ``(net, tax)`` for a gross amount at a percentage-point rate.

    Both components are rounded to two decimals; the tax leg is computed
    as ``gross - net`` after the net leg is rounded, so the two always
    add up exactly to the (rounded) gross.
    """
    if rate == 0:
        return round_money(gross), Decimal("0.00")
    divisor = Decimal("1") + (rate / Decimal("100"))
    net = round_money(gross / divisor)
    tax = round_money(gross - net)
    return net, tax
