"""Transaction-categorization MCP tool.

A small, deliberately readable rule engine that maps a transaction
(vendor + description) to a German accounting category. The rule set
is intentionally short and curated for the demo fixtures; the goal is
to demonstrate the *pattern* of explainable, auditable categorization,
not to replace a full Kontenrahmen mapping.

Each rule carries a human-readable rationale that is returned with the
result so the LLM (and any downstream auditor) can see *why* a match
was made — not just *which* category was picked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import ProductionNotImplementedError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


@dataclass(frozen=True, slots=True)
class _Rule:
    pattern: re.Pattern[str]
    category: str
    rationale: str


_RULES: tuple[_Rule, ...] = (
    _Rule(
        re.compile(
            r"\b(METRO|EDEKA|REWE|Lidl|Kaufland|Großmarkt|Großhandel)\b",
            re.IGNORECASE,
        ),
        "Wareneinkauf",
        "Vendor or description matches a wholesale / grocery supplier.",
    ),
    _Rule(
        re.compile(
            r"\b(Telekom|Vodafone|1\s*&\s*1|O2|Mobilfunk|DSL|Festnetz)\b",
            re.IGNORECASE,
        ),
        "Telekommunikation",
        "Vendor or description matches a telecommunications provider or service.",
    ),
    _Rule(
        re.compile(
            r"\b(Shell|Aral|Esso|Total|Tankstelle|Diesel|Benzin|Tanken|ADAC)\b",
            re.IGNORECASE,
        ),
        "Fahrzeugkosten",
        "Vendor or description matches fuel, Tankstelle, or motoring service.",
    ),
    _Rule(
        re.compile(
            r"\b(Deutsche\s+Post|DHL|Briefporto|Porto|Versandkosten)\b",
            re.IGNORECASE,
        ),
        "Porto",
        "Vendor or description indicates postal or shipping costs.",
    ),
    _Rule(
        re.compile(
            r"\b(OBI|Bauhaus|Hornbach|Werkzeug|Reinigungsmaterial)\b",
            re.IGNORECASE,
        ),
        "Geringwertige Wirtschaftsgüter",
        "Vendor or description indicates low-value tangible goods (Werkzeug, Bauhaus).",
    ),
    _Rule(
        re.compile(
            r"\b(DATEV|Lexoffice|sevDesk|Buchhaltungssoftware)\b",
            re.IGNORECASE,
        ),
        "Buchhaltungssoftware",
        "Vendor or description matches a German accounting-software provider.",
    ),
    _Rule(
        re.compile(
            r"\b(Deutsche\s+Bahn|ICE|Lufthansa|Hotel|Booking\.com)\b",
            re.IGNORECASE,
        ),
        "Reisekosten",
        "Vendor or description indicates travel costs (rail, hotel, airline).",
    ),
)

_FALLBACK_CATEGORY = "Unkategorisiert"
_FALLBACK_RATIONALE = "No categorization rule matched; manual review needed."


def _categorize(haystack: str) -> tuple[str, str, str]:
    """Return ``(category, rationale, confidence)`` for the given text."""
    for rule in _RULES:
        if rule.pattern.search(haystack):
            return rule.category, rule.rationale, "rule_based"
    return _FALLBACK_CATEGORY, _FALLBACK_RATIONALE, "fallback"


def register(server: FastMCP, config: Config) -> None:
    """Register the categorization tool onto ``server``."""

    @server.tool()
    async def categorize_transaction(
        description: str,
        amount_gross: str,
        vendor: str | None = None,
    ) -> dict[str, Any]:
        """Categorize a transaction into a German accounting category.

        Uses a small, explainable rule engine over vendor + description.
        Each rule returns the matched category plus the rationale that
        triggered it, so the result is auditable.

        Args:
            description: Free-text description of the transaction
                (e.g. ``"Diesel Sprinter Lieferfahrzeug"``). Must be
                non-empty if ``vendor`` is omitted.
            amount_gross: Gross amount as a decimal string (e.g.
                ``"238.45"``). Currently echoed back unchanged; reserved
                for amount-aware rules in a future revision.
            vendor: Optional vendor name (e.g. ``"METRO Cash & Carry"``).
                If supplied, takes priority during matching.

        Returns:
            A dictionary with ``category``, ``matched_rule`` (rationale),
            ``confidence`` (``"rule_based"`` or ``"fallback"``), and an
            echo of ``vendor``, ``description``, and ``amount_gross``.

        Raises:
            ValueError: If both ``description`` and ``vendor`` are empty,
                or if ``amount_gross`` is not a valid decimal string.
        """
        description = description.strip()
        vendor_norm = (vendor or "").strip()

        if not description and not vendor_norm:
            raise ValueError(
                "At least one of `description` or `vendor` must be a non-empty string."
            )

        try:
            amount = Decimal(amount_gross)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(
                f"amount_gross must be a decimal string (e.g. '12.30'); got {amount_gross!r}."
            ) from exc

        if config.mode is Mode.DEMO:
            haystack = f"{vendor_norm} {description}".strip()
            category, rationale, confidence = _categorize(haystack)
            return {
                "category": category,
                "matched_rule": rationale,
                "confidence": confidence,
                "vendor": vendor_norm or None,
                "description": description,
                "amount_gross": str(amount),
            }

        raise ProductionNotImplementedError(
            "categorize_transaction is not yet wired to the production BuchhaltIQ API. "
            "Set BUCHHALTIQ_MCP_MODE=demo to use fixture data."
        )
