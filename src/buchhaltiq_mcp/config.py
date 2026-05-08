"""Runtime configuration: demo mode (fixtures) vs production mode (real API)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    """Server operating mode."""

    DEMO = "demo"
    PRODUCTION = "production"


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved server configuration."""

    mode: Mode
    api_key: str | None
    api_base_url: str

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config from environment variables, defaulting to demo mode."""
        raw_mode = os.environ.get("BUCHHALTIQ_MCP_MODE", "demo").strip().lower()
        try:
            mode = Mode(raw_mode)
        except ValueError as exc:
            raise ValueError(
                f"Invalid BUCHHALTIQ_MCP_MODE={raw_mode!r}; expected 'demo' or 'production'."
            ) from exc

        api_key = os.environ.get("BUCHHALTIQ_API_KEY") or None
        api_base_url = os.environ.get(
            "BUCHHALTIQ_API_BASE_URL", "https://api.buchhaltiq.de/v1"
        ).rstrip("/")

        if mode is Mode.PRODUCTION and not api_key:
            raise ValueError(
                "BUCHHALTIQ_MCP_MODE=production requires BUCHHALTIQ_API_KEY to be set."
            )

        return cls(mode=mode, api_key=api_key, api_base_url=api_base_url)
