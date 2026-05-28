"""HTTP client for the BuchhaltIQ backend (production mode).

Thin async wrapper around ``httpx.AsyncClient`` that knows which backend
routes correspond to which MCP tools. Each method maps one MCP-tool
production path to the backend endpoint it wraps.

The client is stateless aside from the underlying httpx connection
pool; instantiate one per ``Config`` and reuse it across calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from buchhaltiq_mcp.config import Config


# Endpoints we know about today. Centralised so a future backend rename
# is a one-line change.
_VALIDATE_PATH = "/api/accounting/validate/{skr}/{account}"
_RESOLVE_PATH = "/api/accounting/resolve"
_INVOICES_LIST_PATH = "/api/user-invoices/list"
_CUSTOMERS_LIST_PATH = "/api/user-invoices/customers"
_TRANSACTIONS_SEARCH_PATH = "/api/user-invoices/transactions"
_MONTHLY_REPORT_PATH = "/api/user-invoices/monthly-report"
_ACCOUNTING_MONTH_OVERVIEW_PATH = "/api/mcp/month-overview/{period_key}"
_HR_EMPLOYEES_PATH = "/api/hr/employees"
_HR_EMPLOYEE_PATH = "/api/hr/employees/{employee_id}"
_HR_TIME_ENTRIES_MONTH_PATH = "/api/hr/time-entries/month/{period_key}"
_HR_TIME_ENTRIES_EMPLOYEE_PATH = "/api/hr/time-entries/employee/{employee_id}"
_HR_MONTH_STATUS_PATH = "/api/hr/months/{period_key}/status"
_HR_ABSENCES_MONTH_PATH = "/api/hr/absences/month/{period_key}"


class BuchhaltIQAPIError(Exception):
    """Raised when the BuchhaltIQ backend returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, *, url: str) -> None:
        super().__init__(f"{status_code} from {url}: {message}")
        self.status_code = status_code
        self.message = message
        self.url = url


class BuchhaltIQClient:
    """Async client for the BuchhaltIQ backend.

    The validate and resolve endpoints are currently public on the
    backend (no auth). The Authorization header is only attached when
    ``config.api_key`` is set, which is forward-looking for the read
    endpoints we expect to wire next (those will use a Firebase ID
    token in ``Authorization: Bearer …``).
    """

    def __init__(self, config: Config, *, timeout: float = 10.0) -> None:
        self._base_url = config.api_base_url
        self._headers: dict[str, str] = {}
        if config.api_key:
            # The MCP-side ``api_key`` is opaque to us. For BuchhaltIQ it
            # is expected to be a Firebase ID token; the backend verifies
            # it via the Firebase Admin SDK.
            self._headers["Authorization"] = f"Bearer {config.api_key}"
        self._timeout = timeout

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        clean_params = {k: v for k, v in params.items() if v is not None} if params else None
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.get(url, headers=self._headers, params=clean_params)
        return self._unwrap(response, url)

    async def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.post(url, headers=self._headers, json=json)
        return self._unwrap(response, url)

    @staticmethod
    def _unwrap(response: httpx.Response, url: str) -> dict[str, Any]:
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise BuchhaltIQAPIError(response.status_code, str(detail), url=url)
        return response.json()

    # ---- MCP-tool-specific methods -------------------------------------------

    async def validate_datev_account(self, *, skr: str, account: str) -> dict[str, Any]:
        """Wrap GET /api/accounting/validate/{skr}/{account}."""
        return await self._get(_VALIDATE_PATH.format(skr=skr, account=account))

    async def resolve_account_assignment(
        self,
        *,
        category_id: str,
        tax_rate: int,
        payment_method: str,
        skr: str,
        gross_amount: str | None = None,
        vendor: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Wrap POST /api/accounting/resolve.

        Note: the backend expects ``tax_rate`` as an integer (0 / 7 / 19),
        not a percentage string. The MCP tool that calls this method is
        responsible for the str→int conversion.
        """
        body: dict[str, Any] = {
            "category_id": category_id,
            "tax_rate": tax_rate,
            "payment_method": payment_method,
            "skr": skr,
        }
        if gross_amount is not None:
            body["gross_amount"] = gross_amount
        if vendor is not None:
            body["vendor"] = vendor
        if description is not None:
            body["description"] = description
        return await self._post(_RESOLVE_PATH, body)

    async def list_invoices(
        self,
        *,
        status: str | None = None,
        customer_id: str | None = None,
        issued_from: str | None = None,
        issued_to: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Wrap GET /api/user-invoices/list. Returns ``{items, count}``."""
        return await self._get(
            _INVOICES_LIST_PATH,
            params={
                "status": status,
                "customer_id": customer_id,
                "issued_from": issued_from,
                "issued_to": issued_to,
                "limit": limit,
            },
        )

    async def list_customers(self) -> dict[str, Any]:
        """Wrap GET /api/user-invoices/customers. Returns ``{items, count}``."""
        return await self._get(_CUSTOMERS_LIST_PATH)

    async def search_transactions(
        self,
        *,
        q: str,
        issued_from: str | None = None,
        issued_to: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Wrap GET /api/user-invoices/transactions. Returns ``{items, count}``."""
        return await self._get(
            _TRANSACTIONS_SEARCH_PATH,
            params={
                "q": q,
                "issued_from": issued_from,
                "issued_to": issued_to,
                "limit": limit,
            },
        )

    async def monthly_report(self, *, year: int, month: int) -> dict[str, Any]:
        """Wrap GET /api/user-invoices/monthly-report. Returns the aggregate dict."""
        return await self._get(_MONTHLY_REPORT_PATH, params={"year": year, "month": month})

    async def accounting_month_overview(self, *, period_key: str) -> dict[str, Any]:
        """Wrap GET /api/mcp/month-overview/{period_key}."""
        return await self._get(_ACCOUNTING_MONTH_OVERVIEW_PATH.format(period_key=period_key))

    async def list_employees(
        self,
        *,
        status: str | None = None,
        employment_type: str | None = None,
    ) -> dict[str, Any]:
        """Wrap GET /api/hr/employees. Returns ``{employees, count}``."""
        return await self._get(
            _HR_EMPLOYEES_PATH,
            params={"status": status, "employmentType": employment_type},
        )

    async def get_employee(self, *, employee_id: str) -> dict[str, Any]:
        """Wrap GET /api/hr/employees/{employee_id}."""
        return await self._get(_HR_EMPLOYEE_PATH.format(employee_id=employee_id))

    async def hr_time_entries_for_month(
        self,
        *,
        period_key: str,
        employee_id: str | None = None,
    ) -> dict[str, Any]:
        """Wrap GET /api/hr/time-entries/month/{period_key}."""
        return await self._get(
            _HR_TIME_ENTRIES_MONTH_PATH.format(period_key=period_key),
            params={"employeeId": employee_id},
        )

    async def hr_time_entries_for_employee(
        self,
        *,
        employee_id: str,
        period_key: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Wrap GET /api/hr/time-entries/employee/{employee_id}."""
        return await self._get(
            _HR_TIME_ENTRIES_EMPLOYEE_PATH.format(employee_id=employee_id),
            params={"periodKey": period_key, "limit": limit},
        )

    async def hr_month_status(self, *, period_key: str) -> dict[str, Any]:
        """Wrap GET /api/hr/months/{period_key}/status."""
        return await self._get(_HR_MONTH_STATUS_PATH.format(period_key=period_key))

    async def hr_absences_for_month(
        self,
        *,
        period_key: str,
        employee_id: str | None = None,
    ) -> dict[str, Any]:
        """Wrap GET /api/hr/absences/month/{period_key}."""
        return await self._get(
            _HR_ABSENCES_MONTH_PATH.format(period_key=period_key),
            params={"employeeId": employee_id},
        )
