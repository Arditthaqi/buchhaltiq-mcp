"""Entry point: ``python -m buchhaltiq_mcp`` or the ``buchhaltiq-mcp`` console script."""

from __future__ import annotations

from buchhaltiq_mcp.server import build_server


def main() -> None:
    """Start the MCP server over stdio."""
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
