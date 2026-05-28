"""Tests for HR / employee MCP tools."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from buchhaltiq_mcp.config import Config
from buchhaltiq_mcp.tools import hr as hr_tool


async def _call(server: FastMCP, name: str, **kwargs: object):
    """Invoke a registered HR tool and unwrap the result payload."""
    result = await server.call_tool(name, kwargs)
    if isinstance(result, tuple) and len(result) >= 2:
        content, structured = result[0], result[1]
    else:
        content, structured = result, None

    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    if structured is not None:
        return structured

    text_block = next(block for block in content if getattr(block, "type", None) == "text")
    return json.loads(text_block.text)


@pytest.fixture
def server_demo(demo_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    hr_tool.register(server, demo_config)
    return server


@pytest.fixture
def server_prod(production_config: Config) -> FastMCP:
    server = FastMCP(name="buchhaltiq-mcp-test")
    hr_tool.register(server, production_config)
    return server


async def test_list_employees_demo_filters_active_and_minimizes_fields(
    server_demo: FastMCP,
) -> None:
    rows = await _call(server_demo, "list_employees", status="active")

    assert [row["id"] for row in rows] == ["emp_001", "emp_002"]
    assert all(row["status"] == "active" for row in rows)
    assert "email" not in rows[0]


async def test_list_employees_demo_can_include_sensitive_fields(server_demo: FastMCP) -> None:
    rows = await _call(
        server_demo,
        "list_employees",
        status="active",
        include_sensitive=True,
    )

    anna = next(row for row in rows if row["id"] == "emp_001")
    assert anna["email"] == "anna.mueller@example.invalid"


async def test_employee_work_summary_demo_separates_shifts_from_work_days(
    server_demo: FastMCP,
) -> None:
    summary = await _call(
        server_demo,
        "get_employee_work_summary",
        employee_id="emp_001",
        period_key="2026-04",
    )

    assert summary["employee"]["display_name"] == "Anna Mueller"
    assert summary["shift_count"] == 4
    assert summary["work_day_count"] == 3
    assert summary["gross_hours"] == 21.5
    assert summary["break_hours"] == 1.25
    assert summary["net_hours"] == 20.25
    assert summary["calculated_wage"] == "303.75"
    assert summary["absence_days"] == 0.5
    assert summary["absence_types"] == {"vacation": 0.5}


async def test_employee_work_summary_demo_can_include_entries(server_demo: FastMCP) -> None:
    summary = await _call(
        server_demo,
        "get_employee_work_summary",
        employee_id="emp_001",
        period_key="2026-04",
        include_entries=True,
    )

    assert len(summary["entries"]) == 4
    late_shift = next(entry for entry in summary["entries"] if entry["id"] == "time_004")
    assert late_shift["gross_minutes"] == 240
    assert late_shift["net_minutes"] == 225


async def test_hr_month_overview_demo_totals_all_active_employees(server_demo: FastMCP) -> None:
    overview = await _call(server_demo, "hr_month_overview", period_key="2026-04")

    assert overview["status"] == "open"
    assert overview["can_edit"] is True
    assert overview["active_employee_count"] == 2
    assert overview["employee_count"] == 2
    assert overview["shift_count"] == 7
    assert overview["work_day_count"] == 6
    assert overview["total_net_hours"] == 40.25
    assert overview["estimated_wage_total"] == "653.75"
    assert overview["absence_days"] == 2.5


async def test_hr_month_overview_invalid_period_raises(server_demo: FastMCP) -> None:
    with pytest.raises(ToolError, match="YYYY-MM"):
        await _call(server_demo, "hr_month_overview", period_key="2026/04")


@respx.mock
async def test_hr_month_overview_production_calls_backend_and_aggregates(
    server_prod: FastMCP,
    production_config: Config,
) -> None:
    base_url = production_config.api_base_url
    respx.get(f"{base_url}/api/hr/employees").mock(
        return_value=httpx.Response(
            200,
            json={
                "employees": [
                    {
                        "id": "emp_real_1",
                        "firstName": "Nora",
                        "lastName": "Nowak",
                        "status": "active",
                        "employmentType": "minijob",
                        "hourlyRate": 16,
                    }
                ],
                "count": 1,
            },
        )
    )
    respx.get(f"{base_url}/api/hr/time-entries/month/2026-04").mock(
        return_value=httpx.Response(
            200,
            json={
                "entries": [
                    {
                        "id": "t1",
                        "employeeId": "emp_real_1",
                        "date": "2026-04-04",
                        "startTime": 600,
                        "endTime": 900,
                        "breakMinutes": 30,
                        "minutesWorked": 270,
                    },
                    {
                        "id": "t2",
                        "employeeId": "emp_real_1",
                        "date": "2026-04-04",
                        "minutesWorked": 180,
                        "breakMinutes": 0,
                    },
                ],
                "count": 2,
            },
        )
    )
    respx.get(f"{base_url}/api/hr/absences/month/2026-04").mock(
        return_value=httpx.Response(200, json={"absences": [], "count": 0})
    )
    respx.get(f"{base_url}/api/hr/months/2026-04/status").mock(
        return_value=httpx.Response(
            200,
            json={"periodKey": "2026-04", "status": "submitted", "canEdit": False},
        )
    )

    overview = await _call(server_prod, "hr_month_overview", period_key="2026-04")

    assert overview["source"] == "production"
    assert overview["status"] == "submitted"
    assert overview["can_edit"] is False
    assert overview["shift_count"] == 2
    assert overview["work_day_count"] == 1
    assert overview["total_net_hours"] == 7.5
    assert overview["estimated_wage_total"] == "120.00"


@respx.mock
async def test_employee_work_summary_production_uses_employee_specific_endpoints(
    server_prod: FastMCP,
    production_config: Config,
) -> None:
    base_url = production_config.api_base_url
    respx.get(f"{base_url}/api/hr/employees/emp_real_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "emp_real_1",
                "firstName": "Nora",
                "lastName": "Nowak",
                "status": "active",
                "employmentType": "minijob",
                "hourlyRate": 16,
            },
        )
    )
    respx.get(f"{base_url}/api/hr/time-entries/employee/emp_real_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "entries": [
                    {
                        "id": "t1",
                        "employeeId": "emp_real_1",
                        "date": "2026-04-05",
                        "minutesWorked": 300,
                        "breakMinutes": 30,
                    }
                ],
                "count": 1,
            },
        )
    )
    respx.get(f"{base_url}/api/hr/absences/month/2026-04").mock(
        return_value=httpx.Response(200, json={"absences": [], "count": 0})
    )
    respx.get(f"{base_url}/api/hr/months/2026-04/status").mock(
        return_value=httpx.Response(200, json={"status": "open", "canEdit": True})
    )

    summary = await _call(
        server_prod,
        "get_employee_work_summary",
        employee_id="emp_real_1",
        period_key="2026-04",
    )

    assert summary["employee"]["display_name"] == "Nora Nowak"
    assert summary["shift_count"] == 1
    assert summary["net_hours"] == 4.5
    assert summary["calculated_wage"] == "72.00"
