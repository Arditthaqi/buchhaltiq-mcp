"""DATEV-related MCP tools.

Wraps the backend's DATEV reference services so the LLM can validate
account numbers against the SKR03 / SKR04 reference table without
having to memorise the chart of accounts. Demo mode reads from a
shipped JSON fixture; production mode will delegate to
``DatevReferenceService`` in the backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.client import BuchhaltIQClient
from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.fixtures import load_datev_accounts
from buchhaltiq_mcp.models import DatevAccount

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


_VALID_SKRS = ("SKR03", "SKR04")


def _normalise_skr(raw: str) -> str:
    cleaned = raw.strip().upper().replace(" ", "")
    if cleaned not in _VALID_SKRS:
        raise ValueError(f"skr must be one of {', '.join(_VALID_SKRS)}; got {raw!r}.")
    return cleaned


def _find_account(skr: str, account: str) -> DatevAccount | None:
    for entry in load_datev_accounts():
        if entry.skr == skr and entry.account == account:
            return entry
    return None


def _suggest_alternatives(skr: str, account: str, *, limit: int = 3) -> list[dict[str, str]]:
    """Best-effort fuzzy suggestions when the exact account is unknown.

    Heuristic: prefer accounts in the same SKR whose number shares a
    common prefix with the requested one. This stays predictable
    (string-prefix only, no edit-distance library), which matters when
    the suggestion list is rendered to the LLM as ground truth.
    """
    pool = [a for a in load_datev_accounts() if a.skr == skr]
    matches: list[tuple[int, DatevAccount]] = []
    for candidate in pool:
        common = 0
        for a, b in zip(account, candidate.account, strict=False):
            if a == b:
                common += 1
            else:
                break
        if common > 0:
            matches.append((common, candidate))
    matches.sort(key=lambda pair: (-pair[0], pair[1].account))
    return [
        {"skr": m.skr, "account": m.account, "title": m.title, "type": m.type}
        for _, m in matches[:limit]
    ]


def _flatten_messages(items: list[dict[str, Any]]) -> list[str]:
    """Reduce backend error/warning objects to flat human-readable strings."""
    flattened: list[str] = []
    for item in items:
        msg = item.get("message")
        code = item.get("code")
        if msg and code:
            flattened.append(f"[{code}] {msg}")
        elif msg:
            flattened.append(str(msg))
    return flattened


def register(server: FastMCP, config: Config) -> None:
    """Register the DATEV tools onto ``server``."""
    client = BuchhaltIQClient(config) if config.mode is Mode.PRODUCTION else None

    @server.tool()
    async def validate_datev_account(skr: str, account: str) -> dict[str, Any]:
        """Validate a DATEV account number against the SKR03 / SKR04 reference.

        Mirrors the backend's ``DatevReferenceService.validate_account``.
        Returns a structured result rather than a boolean so the LLM can
        present the account's title and type to the user when valid, or
        a list of similar accounts when invalid.

        Args:
            skr: Chart of accounts. ``"SKR03"`` or ``"SKR04"``.
            account: Account number as a string (preserves leading zeros
                where SKR04 uses them, e.g. ``"1406"``).

        Returns:
            A dictionary with ``is_valid`` (bool), ``skr``, ``account``,
            and either ``title`` + ``type`` (when valid) or ``errors``
            (a list of human-readable error strings) and ``suggestions``
            (up to three near-matches to help the user correct typos).

        Raises:
            ValueError: If ``skr`` is not SKR03 or SKR04.
        """
        normalised_skr = _normalise_skr(skr)
        account_normalised = account.strip()
        if not account_normalised:
            raise ValueError("account must be a non-empty string.")

        if config.mode is Mode.DEMO:
            entry = _find_account(normalised_skr, account_normalised)
            if entry is not None:
                return {
                    "is_valid": True,
                    "skr": entry.skr,
                    "account": entry.account,
                    "title": entry.title,
                    "type": entry.type,
                    "errors": [],
                    "suggestions": [],
                }
            return {
                "is_valid": False,
                "skr": normalised_skr,
                "account": account_normalised,
                "errors": [
                    f"Account {account_normalised!r} is not present in the "
                    f"{normalised_skr} reference."
                ],
                "suggestions": _suggest_alternatives(normalised_skr, account_normalised),
            }

        # Production mode: delegate to the backend.
        assert client is not None
        backend = await client.validate_datev_account(
            skr=normalised_skr, account=account_normalised
        )
        # Pull the first datev_reference's title to the top level so the
        # LLM can render a human-readable label without diving into the
        # nested structure. Full datev_references is preserved for callers
        # that want the audit trail.
        refs = backend.get("datev_references") or []
        title = refs[0].get("title") if refs else None
        return {
            "is_valid": bool(backend.get("is_valid")),
            "skr": normalised_skr,
            "account": account_normalised,
            "title": title,
            "type": None,  # backend does not classify accounts by type today
            "errors": _flatten_messages(backend.get("errors") or []),
            "warnings": _flatten_messages(backend.get("warnings") or []),
            "suggestions": [],  # backend has no near-match heuristic
            "datev_references": refs,
        }
