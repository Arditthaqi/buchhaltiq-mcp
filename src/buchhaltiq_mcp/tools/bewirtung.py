"""Bewirtung (entertainment) MCP tool.

Implements the German tax rule for business-entertainment expenses
(Bewirtungsbelege): of the net amount, only 70% is income-tax-
deductible for Geschäftsessen (client entertainment); 30% is
non-deductible. Mitarbeiterbewirtung (in-house employee events) is
100% deductible. Input VAT (Vorsteuer) is fully recoverable in both
cases regardless of the income-tax split — this is the part most
non-specialist categorisers get wrong.

Mirrors the BewirtungResult model in the backend (``models.py:139``)
and the calculation in ``receipt_analysis.py:227-263``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import ProductionNotImplementedError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


_TWO_PLACES = Decimal("0.01")
_GESCHAEFTSESSEN_DEDUCTIBLE = Decimal("70")  # § 4 Abs. 5 Nr. 2 EStG
_MITARBEITER_DEDUCTIBLE = Decimal("100")
_SUPPORTED_RATES = (Decimal("0"), Decimal("7"), Decimal("19"))


def _parse_decimal(raw: str, *, field: str) -> Decimal:
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal string (e.g. '119.00'); got {raw!r}.") from exc


def _parse_tax_rate(raw: str) -> Decimal:
    rate = _parse_decimal(raw, field="tax_rate")
    if rate < 1 and rate > 0:
        rate = rate * Decimal("100")
    if rate not in _SUPPORTED_RATES:
        supported = ", ".join(str(r) for r in _SUPPORTED_RATES)
        raise ValueError(f"tax_rate {rate}% is not supported (supported: {supported}%).")
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
    """Register the Bewirtung tool onto ``server``."""

    @server.tool()
    async def apply_bewirtung_rule(
        amount_gross: str,
        tax_rate: str = "19",
        is_employee_event: bool = False,
    ) -> dict[str, Any]:
        """Apply the German Bewirtung deduction rule to an entertainment receipt.

        For Geschäftsessen (client / partner entertainment), only 70% of
        the net amount is income-tax-deductible per § 4 Abs. 5 Nr. 2 EStG.
        For Mitarbeiterbewirtung (in-house employee events), 100% is
        deductible. **Input VAT (Vorsteuer) is fully recoverable in both
        cases** regardless of the income-tax split — this is a common
        source of categorisation errors and is made explicit in the
        result.

        Args:
            amount_gross: Gross amount of the entertainment receipt
                (decimal string, e.g. ``"119.00"``).
            tax_rate: VAT rate as percentage points. Default ``"19"``;
                Restaurantbewirtung is generally 19% in Germany.
                Supported: 0, 7, 19.
            is_employee_event: ``True`` for Mitarbeiterbewirtung
                (100% deductible). ``False`` (default) for
                Geschäftsessen (70% deductible).

        Returns:
            A dictionary with the full split:
            ``amount_gross``, ``amount_net``, ``tax_amount``,
            ``tax_rate``, ``deductible_pct`` (70 or 100),
            ``net_deductible``, ``net_non_deductible``,
            ``vat_recoverable`` (always equals ``tax_amount``),
            ``rule`` (``"Geschäftsessen 70%"`` or
            ``"Mitarbeiterbewirtung 100%"``), ``currency``.

        Raises:
            ValueError: If ``amount_gross`` is invalid or negative,
                or if ``tax_rate`` is unsupported.
        """
        gross = _parse_decimal(amount_gross, field="amount_gross")
        if gross < 0:
            raise ValueError(
                f"amount_gross must be non-negative; got {gross}. "
                "Storno of entertainment expenses is out of scope."
            )

        rate = _parse_tax_rate(tax_rate)
        deductible_pct = (
            _MITARBEITER_DEDUCTIBLE if is_employee_event else _GESCHAEFTSESSEN_DEDUCTIBLE
        )
        rule_name = "Mitarbeiterbewirtung 100%" if is_employee_event else "Geschäftsessen 70%"

        if config.mode is Mode.DEMO:
            net, tax = _split_gross(gross, rate)
            net_deductible = _round(net * deductible_pct / Decimal("100"))
            net_non_deductible = _round(net - net_deductible)
            return {
                "amount_gross": str(_round(gross)),
                "amount_net": str(net),
                "tax_amount": str(tax),
                "tax_rate": str(rate),
                "deductible_pct": int(deductible_pct),
                "net_deductible": str(net_deductible),
                "net_non_deductible": str(net_non_deductible),
                "vat_recoverable": str(tax),
                "rule": rule_name,
                "currency": "EUR",
            }

        raise ProductionNotImplementedError(
            "apply_bewirtung_rule is not yet wired to the production "
            "BuchhaltIQ API. Set BUCHHALTIQ_MCP_MODE=demo to use the "
            "in-process implementation."
        )
