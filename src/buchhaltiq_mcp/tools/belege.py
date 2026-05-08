"""Beleg-related (receipt) MCP tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.client import BuchhaltIQClient
from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.fixtures import load_belege
from buchhaltiq_mcp.models import Beleg

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


def _matches(beleg: Beleg, needle: str) -> bool:
    haystack = f"{beleg.vendor} {beleg.description}".lower()
    return needle in haystack


def _search_demo_belege(query: str, limit: int) -> list[Beleg]:
    needle = query.lower()
    matches = [b for b in load_belege() if _matches(b, needle)]
    matches.sort(key=lambda b: b.issue_date, reverse=True)
    return matches[:limit]


def register(server: FastMCP, config: Config) -> None:
    """Register the Beleg tools onto ``server``."""
    client = BuchhaltIQClient(config) if config.mode is Mode.PRODUCTION else None

    @server.tool()
    async def search_belege(query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text search over BuchhaltIQ receipts (``Belege``).

        The query is matched case-insensitively as a substring against both the
        vendor name and the free-text description of each receipt.

        Args:
            query: Search term, e.g. ``"METRO"``, ``"Diesel"``, ``"Telekom"``.
                Must be a non-empty string after trimming.
            limit: Maximum number of receipts to return (default 20, max 100).
                Results are ordered newest-first by issue date.

        Returns:
            A list of receipt dictionaries with ``id``, ``issue_date``,
            ``vendor``, ``amount_gross``, ``category``, and ``description``.

        Raises:
            ValueError: If ``query`` is empty or whitespace.
        """
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be a non-empty string.")

        capped_limit = max(1, min(limit, 100))

        if config.mode is Mode.DEMO:
            results = _search_demo_belege(normalized_query, capped_limit)
            return [b.model_dump(mode="json") for b in results]

        # Production mode: delegate to the backend, which substring-matches
        # the user's bank transactions as Belege.
        assert client is not None
        backend = await client.search_transactions(q=normalized_query, limit=capped_limit)
        return list(backend.get("items") or [])
