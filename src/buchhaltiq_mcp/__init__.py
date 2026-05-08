"""buchhaltiq-mcp: MCP server for the BuchhaltIQ accounting product."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("buchhaltiq-mcp")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
