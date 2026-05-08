"""Mixed-tax receipt-splitting MCP tool.

Mirrors the position-splitting logic the backend uses for receipts
that span multiple VAT rates (a typical Edeka / METRO trip with food
at 7% and non-food at 19%). The tool walks the position list,
computes the net / tax split per position, aggregates per rate, and
flags any mismatch against an expected gross total.

Reference in backend: ``receipt_analysis.py:153-183`` (has_mixed_tax)
and ``dxso_xml_builder.py`` (the position-emit pipeline).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import ProductionNotImplementedError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


_TWO_PLACES = Decimal("0.01")
_SUPPORTED_RATES = (Decimal("0"), Decimal("7"), Decimal("19"))


class PositionInput(BaseModel):
    """A single line item on a receipt to be split."""

    model_config = ConfigDict(extra="forbid")

    amount_gross: str
    tax_rate: str
    description: str | None = None


def _parse_decimal(raw: str, *, field: str, position_idx: int | None = None) -> Decimal:
    where = f" (position {position_idx})" if position_idx is not None else ""
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field}{where} must be a decimal string; got {raw!r}.") from exc


def _parse_tax_rate(raw: str, *, position_idx: int) -> Decimal:
    rate = _parse_decimal(raw, field="tax_rate", position_idx=position_idx)
    if rate < 1 and rate > 0:
        rate = rate * Decimal("100")
    if rate not in _SUPPORTED_RATES:
        supported = ", ".join(str(r) for r in _SUPPORTED_RATES)
        raise ValueError(
            f"tax_rate {rate}% (position {position_idx}) is not supported "
            f"(supported: {supported}%)."
        )
    return rate


def _round(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _split_gross(gross: Decimal, rate: Decimal) -> tuple[Decimal, Decimal]:
    if rate == 0:
        return _round(gross), Decimal("0.00")
    divisor = Decimal("1") + (rate / Decimal("100"))
    net = _round(gross / divisor)
    tax = _round(gross - net)
    return net, tax


def register(server: FastMCP, config: Config) -> None:
    """Register the split tool onto ``server``."""

    @server.tool()
    async def split_mixed_tax_receipt(
        positions: list[PositionInput],
        expected_total_gross: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate a list of positions into a per-rate VAT breakdown.

        Walks the positions, splits each one into net / tax using the
        per-position rate, then groups by rate to produce the breakdown
        a Steuerberater needs to post the receipt correctly. ``has_mixed_tax``
        flips to ``True`` as soon as more than one rate is present.

        Optionally, ``expected_total_gross`` enables a sanity check: if
        the sum of position grosses differs from this value, the result
        carries a non-empty ``warnings`` list (the LLM can then ask the
        user to recount or correct).

        Args:
            positions: One entry per line item. Each has
                ``amount_gross`` (decimal string, gross),
                ``tax_rate`` (percentage points or fraction), and
                an optional ``description``. Must contain at least
                one position.
            expected_total_gross: Optional decimal string. If supplied
                and the sum of position grosses differs, a warning is
                added to the result.

        Returns:
            A dictionary with ``positions`` (each enriched with
            ``amount_net``, ``tax_amount``, normalised ``tax_rate``),
            ``total_gross``, ``total_net``, ``total_tax``,
            ``has_mixed_tax`` (bool), ``breakdown_by_rate`` (a
            dict keyed by rate string, each value a sub-dict with
            ``gross``, ``net``, ``tax``, ``position_count``),
            ``warnings`` (list of strings), and ``currency``.

        Raises:
            ValueError: If ``positions`` is empty, any position has
                an unsupported rate, or any decimal field is malformed.
        """
        if not positions:
            raise ValueError("positions must contain at least one entry.")

        enriched: list[dict[str, Any]] = []
        per_rate: dict[Decimal, dict[str, Decimal | int]] = {}
        total_gross = Decimal("0.00")
        total_net = Decimal("0.00")
        total_tax = Decimal("0.00")

        for idx, pos in enumerate(positions):
            gross = _parse_decimal(pos.amount_gross, field="amount_gross", position_idx=idx)
            if gross < 0:
                raise ValueError(
                    f"amount_gross (position {idx}) must be non-negative; got {gross}."
                )
            rate = _parse_tax_rate(pos.tax_rate, position_idx=idx)
            net, tax = _split_gross(gross, rate)

            enriched.append(
                {
                    "description": pos.description,
                    "amount_gross": str(_round(gross)),
                    "amount_net": str(net),
                    "tax_amount": str(tax),
                    "tax_rate": str(rate),
                }
            )

            bucket = per_rate.setdefault(
                rate,
                {
                    "gross": Decimal("0.00"),
                    "net": Decimal("0.00"),
                    "tax": Decimal("0.00"),
                    "position_count": 0,
                },
            )
            bucket["gross"] = bucket["gross"] + gross  # type: ignore[operator]
            bucket["net"] = bucket["net"] + net  # type: ignore[operator]
            bucket["tax"] = bucket["tax"] + tax  # type: ignore[operator]
            bucket["position_count"] = bucket["position_count"] + 1  # type: ignore[operator]

            total_gross += gross
            total_net += net
            total_tax += tax

        warnings: list[str] = []
        if expected_total_gross is not None:
            expected = _parse_decimal(expected_total_gross, field="expected_total_gross")
            if _round(expected) != _round(total_gross):
                warnings.append(
                    f"Sum of position grosses ({_round(total_gross)}) does not match "
                    f"expected_total_gross ({_round(expected)}). Difference: "
                    f"{_round(total_gross - expected)}."
                )

        if config.mode is Mode.DEMO:
            breakdown_by_rate = {
                str(rate): {
                    "gross": str(_round(b["gross"])),  # type: ignore[arg-type]
                    "net": str(_round(b["net"])),  # type: ignore[arg-type]
                    "tax": str(_round(b["tax"])),  # type: ignore[arg-type]
                    "position_count": b["position_count"],
                }
                for rate, b in sorted(per_rate.items())
            }
            return {
                "positions": enriched,
                "total_gross": str(_round(total_gross)),
                "total_net": str(_round(total_net)),
                "total_tax": str(_round(total_tax)),
                "has_mixed_tax": len(per_rate) > 1,
                "breakdown_by_rate": breakdown_by_rate,
                "warnings": warnings,
                "currency": "EUR",
            }

        raise ProductionNotImplementedError(
            "split_mixed_tax_receipt is not yet wired to the production "
            "BuchhaltIQ API. Set BUCHHALTIQ_MCP_MODE=demo to use the "
            "in-process implementation."
        )
