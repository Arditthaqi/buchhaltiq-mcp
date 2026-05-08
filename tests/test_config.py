"""Tests for runtime configuration parsing."""

from __future__ import annotations

import pytest

from buchhaltiq_mcp.config import Config, Mode


def test_defaults_to_demo_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUCHHALTIQ_MCP_MODE", raising=False)
    monkeypatch.delenv("BUCHHALTIQ_API_KEY", raising=False)
    monkeypatch.delenv("BUCHHALTIQ_API_BASE_URL", raising=False)
    cfg = Config.from_env()
    assert cfg.mode is Mode.DEMO
    assert cfg.api_key is None
    assert cfg.api_base_url == "https://api.buchhaltiq.de/v1"


def test_invalid_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUCHHALTIQ_MCP_MODE", "staging")
    with pytest.raises(ValueError, match="Invalid BUCHHALTIQ_MCP_MODE"):
        Config.from_env()


def test_production_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUCHHALTIQ_MCP_MODE", "production")
    monkeypatch.delenv("BUCHHALTIQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="requires BUCHHALTIQ_API_KEY"):
        Config.from_env()


def test_production_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUCHHALTIQ_MCP_MODE", "production")
    monkeypatch.setenv("BUCHHALTIQ_API_KEY", "secret-token")
    cfg = Config.from_env()
    assert cfg.mode is Mode.PRODUCTION
    assert cfg.api_key == "secret-token"


def test_base_url_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUCHHALTIQ_MCP_MODE", "demo")
    monkeypatch.setenv("BUCHHALTIQ_API_BASE_URL", "https://example.com/api/v1/")
    cfg = Config.from_env()
    assert cfg.api_base_url == "https://example.com/api/v1"
