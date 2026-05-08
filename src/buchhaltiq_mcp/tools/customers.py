"""Customer-related MCP tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import NotFoundError, ProductionNotImplementedError
from buchhaltiq_mcp.fixtures import load_customers
from buchhaltiq_mcp.models import Customer

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


def _find_demo_customer(customer_id: str) -> Customer:
    for customer in load_customers():
        if customer.id == customer_id:
            return customer
    raise NotFoundError(f"No customer with id={customer_id!r} exists.")


def register(server: FastMCP, config: Config) -> None:
    """Register the customer tools onto ``server``."""

    @server.tool()
    async def get_customer(customer_id: str) -> dict[str, Any]:
        """Fetch a single BuchhaltIQ customer by ID.

        Args:
            customer_id: Stable identifier of the customer
                (e.g. ``cust_001``). Must be a non-empty string.

        Returns:
            The customer record as a dictionary, including ``id``, ``name``,
            ``contact_email``, ``city``, and ``country``.

        Raises:
            ValueError: If ``customer_id`` is empty or whitespace.
            NotFoundError: If no customer with the given ID exists.
        """
        normalized = customer_id.strip()
        if not normalized:
            raise ValueError("customer_id must be a non-empty string.")

        if config.mode is Mode.DEMO:
            customer = _find_demo_customer(normalized)
            return customer.model_dump(mode="json")

        raise ProductionNotImplementedError(
            "get_customer is not yet wired to the production BuchhaltIQ API. "
            "Set BUCHHALTIQ_MCP_MODE=demo to use fixture data."
        )
