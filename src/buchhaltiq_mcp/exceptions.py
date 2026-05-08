"""Domain-specific exceptions exposed to MCP clients."""

from __future__ import annotations


class BuchhaltIQError(Exception):
    """Base class for buchhaltiq-mcp errors surfaced to the caller."""


class NotFoundError(BuchhaltIQError):
    """Raised when a requested resource (customer, invoice, …) does not exist."""


class ProductionNotImplementedError(BuchhaltIQError):
    """Raised when a tool is invoked in production mode but no real API binding exists yet."""
