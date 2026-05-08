"""FastMCP server factory."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from buchhaltiq_mcp import __version__
from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import register_all


def build_server(config: Config | None = None) -> FastMCP:
    """Construct a fully-wired :class:`FastMCP` server.

    Args:
        config: Resolved configuration. When omitted, configuration is read from
            environment variables via :meth:`Config.from_env`.

    Returns:
        A FastMCP instance ready for ``.run()`` (stdio transport).
    """
    if config is None:
        config = Config.from_env()

    server = FastMCP(
        name="buchhaltiq-mcp",
        instructions=(
            "MCP server for the BuchhaltIQ accounting product. Currently running in "
            f"{config.mode.value!r} mode (server version {__version__})."
        ),
    )
    register_all(server, config)
    return server
