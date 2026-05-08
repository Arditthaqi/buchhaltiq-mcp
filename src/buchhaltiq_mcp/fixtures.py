"""Fixture loader for demo mode.

Reads JSON fixtures from ``data/`` (when running from a source checkout) or from
``buchhaltiq_mcp/_fixtures/`` inside the installed wheel.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from buchhaltiq_mcp.models import Beleg, Customer, DatevAccount, Invoice

_REPO_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_raw(name: str) -> list[dict[str, Any]]:
    """Locate ``<name>.json`` in either the repo's data/ or the installed package."""
    repo_path = _REPO_DATA_DIR / f"{name}.json"
    if repo_path.is_file():
        return json.loads(repo_path.read_text(encoding="utf-8"))

    package_files = resources.files("buchhaltiq_mcp").joinpath("_fixtures")
    fixture_path = package_files.joinpath(f"{name}.json")
    if fixture_path.is_file():
        return json.loads(fixture_path.read_text(encoding="utf-8"))

    raise FileNotFoundError(
        f"Fixture {name!r} not found in either {_REPO_DATA_DIR} or the installed package."
    )


@lru_cache(maxsize=1)
def load_customers() -> list[Customer]:
    """Return all demo customers."""
    return [Customer.model_validate(row) for row in _load_raw("customers")]


@lru_cache(maxsize=1)
def load_invoices() -> list[Invoice]:
    """Return all demo invoices."""
    return [Invoice.model_validate(row) for row in _load_raw("invoices")]


@lru_cache(maxsize=1)
def load_belege() -> list[Beleg]:
    """Return all demo receipts."""
    return [Beleg.model_validate(row) for row in _load_raw("belege")]


@lru_cache(maxsize=1)
def load_datev_accounts() -> list[DatevAccount]:
    """Return the SKR03 / SKR04 account reference table."""
    return [DatevAccount.model_validate(row) for row in _load_raw("datev_accounts")]
