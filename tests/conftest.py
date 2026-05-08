"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from buchhaltiq_mcp.config import Config, Mode


@pytest.fixture
def demo_config() -> Config:
    """A Config wired for demo mode with no API key."""
    return Config(mode=Mode.DEMO, api_key=None, api_base_url="https://api.buchhaltiq.de/v1")


@pytest.fixture
def production_config() -> Config:
    """A Config wired for production mode with a placeholder API key."""
    return Config(
        mode=Mode.PRODUCTION,
        api_key="test-key-not-real",
        api_base_url="https://api.buchhaltiq.de/v1",
    )
