"""HR / employee MCP tools.

The backend already owns employee master data, time entries, absences and HR
month locks. This module turns those raw endpoints into a compact MCP surface
that answers the questions users ask in natural language: who worked, how often,
how many net hours, which absences matter, and whether the month is still editable.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from buchhaltiq_mcp.client import BuchhaltIQClient
from buchhaltiq_mcp.config import Mode
from buchhaltiq_mcp.exceptions import NotFoundError
from buchhaltiq_mcp.fixtures import (
    load_hr_absences,
    load_hr_employees,
    load_hr_month_statuses,
    load_hr_time_entries,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from buchhaltiq_mcp.config import Config


_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")
_VALID_EMPLOYEE_STATUSES = {"active", "inactive"}
_VALID_EMPLOYMENT_TYPES = {"minijob", "parttime", "fulltime"}
_INACTIVE_ABSENCE_STATUSES = {"cancelled", "rejected"}
_CENT = Decimal("0.01")


def _validate_period_key(period_key: str) -> tuple[int, int]:
    if not _PERIOD_RE.match(period_key):
        raise ValueError("period_key must use YYYY-MM format.")
    year_raw, month_raw = period_key.split("-")
    year = int(year_raw)
    month = int(month_raw)
    if not (2000 <= year <= 2100):
        raise ValueError("period_key year must be between 2000 and 2100.")
    if not (1 <= month <= 12):
        raise ValueError("period_key month must be between 01 and 12.")
    return year, month


def _period_bounds(period_key: str) -> tuple[date, date]:
    year, month = _validate_period_key(period_key)
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1).replace(day=1)
        end = date.fromordinal(end.toordinal() - 1)
    return start, end


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
    return None


def _period_key_from_date(value: Any) -> str | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return f"{parsed.year}-{parsed.month:02d}"


def _int_value(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _hours(minutes: int) -> float:
    return round(minutes / 60, 2)


def _duration_minutes(start_time: Any, end_time: Any) -> int | None:
    if start_time is None or end_time is None:
        return None
    start = _int_value(start_time, default=-1)
    end = _int_value(end_time, default=-1)
    if not (0 <= start <= 1439 and 0 <= end <= 1439):
        return None
    if end < start:
        return (24 * 60 - start) + end
    return end - start


def _entry_net_minutes(entry: dict[str, Any]) -> int:
    minutes = _int_value(entry.get("minutesWorked") or entry.get("minutes_worked"))
    break_minutes = _int_value(entry.get("breakMinutes") or entry.get("break_minutes"))
    duration = _duration_minutes(entry.get("startTime"), entry.get("endTime"))
    if duration is not None:
        duration_net = max(duration - break_minutes, 0)
        if minutes == duration:
            return duration_net
        if minutes == duration_net:
            return minutes
    return max(minutes - break_minutes, 0)


def _entry_gross_minutes(entry: dict[str, Any]) -> int:
    duration = _duration_minutes(entry.get("startTime"), entry.get("endTime"))
    if duration is not None:
        return duration
    return _int_value(entry.get("minutesWorked") or entry.get("minutes_worked"))


def _entry_employee_id(entry: dict[str, Any]) -> str:
    return str(entry.get("employeeId") or entry.get("employee_id") or "").strip()


def _employee_id(employee: dict[str, Any]) -> str:
    raw_id = employee.get("id") or employee.get("employeeId") or employee.get("employee_id") or ""
    return str(raw_id).strip()


def _employee_display_name(employee: dict[str, Any]) -> str:
    first = str(employee.get("firstName") or employee.get("first_name") or "").strip()
    last = str(employee.get("lastName") or employee.get("last_name") or "").strip()
    display = f"{first} {last}".strip()
    return display or _employee_id(employee)


def _employee_status(employee: dict[str, Any]) -> str:
    return str(employee.get("status") or "active").strip().lower()


def _project_employee(
    employee: dict[str, Any],
    *,
    include_sensitive: bool = False,
) -> dict[str, Any]:
    projected = {
        "id": _employee_id(employee),
        "display_name": _employee_display_name(employee),
        "first_name": employee.get("firstName") or employee.get("first_name"),
        "last_name": employee.get("lastName") or employee.get("last_name"),
        "status": _employee_status(employee),
        "employment_type": employee.get("employmentType") or employee.get("employment_type"),
        "hourly_rate": employee.get("hourlyRate") or employee.get("hourly_rate"),
        "weekly_hours": employee.get("weeklyHours") or employee.get("weekly_hours"),
        "datev_personnel_number": employee.get("datevPersonnelNumber")
        or employee.get("datev_personnel_number"),
        "entry_date": _date_to_iso(employee.get("entryDate") or employee.get("entry_date")),
        "exit_date": _date_to_iso(employee.get("exitDate") or employee.get("exit_date")),
    }
    if include_sensitive:
        projected.update(
            {
                "email": employee.get("email"),
                "phone": employee.get("phone"),
                "cost_center_id": employee.get("costCenterId") or employee.get("cost_center_id"),
                "datev_locked": employee.get("datevLocked") or employee.get("datev_locked"),
                "datev_synced": employee.get("datevSynced") or employee.get("datev_synced"),
            }
        )
    return projected


def _date_to_iso(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _project_entry(entry: dict[str, Any]) -> dict[str, Any]:
    gross = _entry_gross_minutes(entry)
    net = _entry_net_minutes(entry)
    break_minutes = _int_value(entry.get("breakMinutes") or entry.get("break_minutes"))
    return {
        "id": entry.get("id"),
        "employee_id": _entry_employee_id(entry),
        "date": _date_to_iso(entry.get("date")),
        "start_time": entry.get("startTime"),
        "end_time": entry.get("endTime"),
        "gross_minutes": gross,
        "break_minutes": break_minutes,
        "net_minutes": net,
        "gross_hours": _hours(gross),
        "break_hours": _hours(break_minutes),
        "net_hours": _hours(net),
        "source": entry.get("source"),
        "notes": entry.get("notes"),
    }


def _absence_employee_id(absence: dict[str, Any]) -> str:
    return str(absence.get("employeeId") or absence.get("employee_id") or "").strip()


def _absence_overlaps_period(absence: dict[str, Any], period_key: str) -> bool:
    if period_key in (absence.get("affectedPeriodKeys") or []):
        return True
    if absence.get("periodKey") == period_key:
        return True
    start, end = _period_bounds(period_key)
    absence_start = _parse_date(absence.get("startDate") or absence.get("start_date"))
    absence_end = _parse_date(absence.get("endDate") or absence.get("end_date")) or absence_start
    if absence_start is None or absence_end is None:
        return False
    return max(start, absence_start) <= min(end, absence_end)


def _absence_days(absence: dict[str, Any], period_key: str) -> Decimal:
    status = str(absence.get("status") or "approved").lower()
    if status in _INACTIVE_ABSENCE_STATUSES:
        return Decimal("0")
    start, end = _period_bounds(period_key)
    absence_start = _parse_date(absence.get("startDate") or absence.get("start_date"))
    absence_end = _parse_date(absence.get("endDate") or absence.get("end_date")) or absence_start
    if absence_start is None or absence_end is None:
        return Decimal("0")
    overlap_start = max(start, absence_start)
    overlap_end = min(end, absence_end)
    if overlap_start > overlap_end:
        return Decimal("0")
    if bool(absence.get("isHalfDay") or absence.get("is_half_day")):
        return Decimal("0.5")
    return Decimal(str((overlap_end - overlap_start).days + 1))


def _project_absence(absence: dict[str, Any], period_key: str) -> dict[str, Any]:
    days = _absence_days(absence, period_key)
    return {
        "id": absence.get("id"),
        "employee_id": _absence_employee_id(absence),
        "type": absence.get("type"),
        "status": absence.get("status") or "approved",
        "start_date": _date_to_iso(absence.get("startDate") or absence.get("start_date")),
        "end_date": _date_to_iso(absence.get("endDate") or absence.get("end_date")),
        "days_in_period": float(days),
        "is_half_day": bool(absence.get("isHalfDay") or absence.get("is_half_day")),
        "eau_status": absence.get("eauStatus") or absence.get("eau_status"),
    }


def _summarize_employee(
    *,
    period_key: str,
    employee: dict[str, Any],
    entries: list[dict[str, Any]],
    absences: list[dict[str, Any]],
    include_entries: bool,
) -> dict[str, Any]:
    projected_employee = _project_employee(employee)
    sorted_entries = sorted(
        entries,
        key=lambda item: (_date_to_iso(item.get("date")) or "", _int_value(item.get("startTime"))),
    )
    work_days = sorted(
        {
            entry_date.isoformat()
            for entry in sorted_entries
            if (entry_date := _parse_date(entry.get("date"))) is not None
        }
    )
    gross_minutes = sum(_entry_gross_minutes(entry) for entry in sorted_entries)
    break_minutes = sum(
        _int_value(entry.get("breakMinutes") or entry.get("break_minutes"))
        for entry in sorted_entries
    )
    net_minutes = sum(_entry_net_minutes(entry) for entry in sorted_entries)

    hourly_rate = _decimal_value(projected_employee.get("hourly_rate"))
    calculated_wage = None
    if hourly_rate is not None:
        calculated_wage = hourly_rate * (Decimal(net_minutes) / Decimal(60))

    projected_absences = [
        _project_absence(absence, period_key)
        for absence in absences
        if _absence_overlaps_period(absence, period_key)
    ]
    absence_days = sum(
        (Decimal(str(item["days_in_period"])) for item in projected_absences),
        Decimal("0"),
    )
    absence_types: dict[str, float] = {}
    for absence in projected_absences:
        key = str(absence.get("type") or "other")
        absence_types[key] = round(
            absence_types.get(key, 0.0) + float(absence["days_in_period"]),
            2,
        )

    summary: dict[str, Any] = {
        "period_key": period_key,
        "employee": projected_employee,
        "shift_count": len(sorted_entries),
        "work_day_count": len(work_days),
        "work_days": work_days,
        "gross_minutes": gross_minutes,
        "break_minutes": break_minutes,
        "net_minutes": net_minutes,
        "gross_hours": _hours(gross_minutes),
        "break_hours": _hours(break_minutes),
        "net_hours": _hours(net_minutes),
        "calculated_wage": _money(calculated_wage),
        "absence_count": len(projected_absences),
        "absence_days": float(absence_days),
        "absence_types": absence_types,
    }
    if include_entries:
        summary["entries"] = [_project_entry(entry) for entry in sorted_entries]
        summary["absences"] = projected_absences
    return summary


def _coerce_rows(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get(key) or payload.get("items") or []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _demo_month_status(period_key: str) -> dict[str, Any]:
    for status in load_hr_month_statuses():
        if status.get("periodKey") == period_key or status.get("period_key") == period_key:
            return dict(status)
    return {"periodKey": period_key, "status": "open", "canEdit": True, "payroll": {}}


def _normalize_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().lower()
    if normalized not in _VALID_EMPLOYEE_STATUSES:
        raise ValueError("status must be 'active' or 'inactive'.")
    return normalized


def _normalize_employment_type(employment_type: str | None) -> str | None:
    if employment_type is None:
        return None
    normalized = employment_type.strip().lower()
    if normalized not in _VALID_EMPLOYMENT_TYPES:
        raise ValueError("employment_type must be 'minijob', 'parttime', or 'fulltime'.")
    return normalized


def _filter_employees(
    employees: list[dict[str, Any]],
    *,
    status: str | None = None,
    employment_type: str | None = None,
) -> list[dict[str, Any]]:
    rows = employees
    if status is not None:
        rows = [employee for employee in rows if _employee_status(employee) == status]
    if employment_type is not None:
        rows = [
            employee
            for employee in rows
            if str(employee.get("employmentType") or employee.get("employment_type") or "").lower()
            == employment_type
        ]
    return rows


def _filter_entries_for_period(
    entries: list[dict[str, Any]],
    *,
    period_key: str,
    employee_id: str | None = None,
) -> list[dict[str, Any]]:
    result = []
    for entry in entries:
        entry_period = (
            entry.get("periodKey")
            or entry.get("period_key")
            or _period_key_from_date(entry.get("date"))
        )
        if entry_period != period_key:
            continue
        if employee_id is not None and _entry_employee_id(entry) != employee_id:
            continue
        result.append(entry)
    return result


def _filter_absences_for_period(
    absences: list[dict[str, Any]],
    *,
    period_key: str,
    employee_id: str | None = None,
) -> list[dict[str, Any]]:
    result = []
    for absence in absences:
        if not _absence_overlaps_period(absence, period_key):
            continue
        if employee_id is not None and _absence_employee_id(absence) != employee_id:
            continue
        result.append(absence)
    return result


def _build_month_overview(
    *,
    period_key: str,
    employees: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    absences: list[dict[str, Any]],
    month_status: dict[str, Any],
    include_entries: bool,
    source: str,
) -> dict[str, Any]:
    employees_by_id = {
        _employee_id(employee): employee for employee in employees if _employee_id(employee)
    }
    relevant_ids = {
        employee_id
        for employee_id, employee in employees_by_id.items()
        if _employee_status(employee) == "active"
    }
    relevant_ids.update(_entry_employee_id(entry) for entry in entries if _entry_employee_id(entry))
    relevant_ids.update(
        _absence_employee_id(absence) for absence in absences if _absence_employee_id(absence)
    )

    summaries = []
    for employee_id in sorted(relevant_ids):
        employee = employees_by_id.get(employee_id) or {
            "id": employee_id,
            "firstName": "",
            "lastName": employee_id,
            "status": "unknown",
        }
        employee_entries = [entry for entry in entries if _entry_employee_id(entry) == employee_id]
        employee_absences = [
            absence for absence in absences if _absence_employee_id(absence) == employee_id
        ]
        summaries.append(
            _summarize_employee(
                period_key=period_key,
                employee=employee,
                entries=employee_entries,
                absences=employee_absences,
                include_entries=include_entries,
            )
        )

    summaries.sort(key=lambda item: item["employee"]["display_name"])

    wage_total = sum(
        (
            Decimal(summary["calculated_wage"])
            for summary in summaries
            if summary.get("calculated_wage") is not None
        ),
        Decimal("0"),
    )
    status_value = month_status.get("status") or "open"
    can_edit = month_status.get("canEdit")
    if can_edit is None:
        can_edit = month_status.get("can_edit")
    if can_edit is None:
        can_edit = status_value == "open"

    return {
        "period_key": period_key,
        "source": source,
        "status": status_value,
        "can_edit": bool(can_edit),
        "payroll": month_status.get("payroll") or {},
        "active_employee_count": sum(
            1 for employee in employees if _employee_status(employee) == "active"
        ),
        "employee_count": len(summaries),
        "employees_with_entries": sum(1 for summary in summaries if summary["shift_count"] > 0),
        "shift_count": sum(summary["shift_count"] for summary in summaries),
        "work_day_count": sum(summary["work_day_count"] for summary in summaries),
        "total_gross_minutes": sum(summary["gross_minutes"] for summary in summaries),
        "total_break_minutes": sum(summary["break_minutes"] for summary in summaries),
        "total_net_minutes": sum(summary["net_minutes"] for summary in summaries),
        "total_gross_hours": _hours(sum(summary["gross_minutes"] for summary in summaries)),
        "total_break_hours": _hours(sum(summary["break_minutes"] for summary in summaries)),
        "total_net_hours": _hours(sum(summary["net_minutes"] for summary in summaries)),
        "estimated_wage_total": _money(wage_total),
        "absence_count": sum(summary["absence_count"] for summary in summaries),
        "absence_days": round(sum(float(summary["absence_days"]) for summary in summaries), 2),
        "employee_summaries": summaries,
    }


def register(server: FastMCP, config: Config) -> None:
    """Register HR tools onto ``server``."""
    client = BuchhaltIQClient(config) if config.mode is Mode.PRODUCTION else None

    @server.tool()
    async def list_employees(
        status: str | None = None,
        employment_type: str | None = None,
        limit: int = 100,
        include_sensitive: bool = False,
    ) -> list[dict[str, Any]]:
        """List BuchhaltIQ employees with optional status and employment-type filters.

        By default the result is field-minimized. Set ``include_sensitive`` only
        when the user explicitly asks for contact or DATEV-lock metadata.
        """
        normalized_status = _normalize_status(status)
        normalized_type = _normalize_employment_type(employment_type)
        capped_limit = max(1, min(limit, 200))

        if config.mode is Mode.DEMO:
            employees = _filter_employees(
                load_hr_employees(),
                status=normalized_status,
                employment_type=normalized_type,
            )
        else:
            assert client is not None
            payload = await client.list_employees(
                status=normalized_status,
                employment_type=normalized_type,
            )
            employees = _coerce_rows(payload, "employees")

        projected = [
            _project_employee(employee, include_sensitive=include_sensitive)
            for employee in employees
        ]
        projected.sort(key=lambda employee: employee["display_name"])
        return projected[:capped_limit]

    @server.tool()
    async def get_employee_work_summary(
        employee_id: str,
        period_key: str,
        include_entries: bool = False,
    ) -> dict[str, Any]:
        """Summarize one employee's work for a month.

        The summary separates ``shift_count`` from ``work_day_count``. Split
        shifts on the same calendar day therefore count as multiple shifts but
        one actual work day.
        """
        employee_id = employee_id.strip()
        if not employee_id:
            raise ValueError("employee_id must be non-empty.")
        _validate_period_key(period_key)

        if config.mode is Mode.DEMO:
            employees = load_hr_employees()
            employee = next((row for row in employees if _employee_id(row) == employee_id), None)
            if employee is None:
                raise NotFoundError(f"Employee not found: {employee_id}")
            entries = _filter_entries_for_period(
                load_hr_time_entries(),
                period_key=period_key,
                employee_id=employee_id,
            )
            absences = _filter_absences_for_period(
                load_hr_absences(),
                period_key=period_key,
                employee_id=employee_id,
            )
            month_status = _demo_month_status(period_key)
        else:
            assert client is not None
            employee = await client.get_employee(employee_id=employee_id)
            entries_payload = await client.hr_time_entries_for_employee(
                employee_id=employee_id,
                period_key=period_key,
                limit=500,
            )
            absences_payload = await client.hr_absences_for_month(
                period_key=period_key,
                employee_id=employee_id,
            )
            month_status = await client.hr_month_status(period_key=period_key)
            entries = _coerce_rows(entries_payload, "entries")
            absences = _coerce_rows(absences_payload, "absences")

        summary = _summarize_employee(
            period_key=period_key,
            employee=employee,
            entries=entries,
            absences=absences,
            include_entries=include_entries,
        )
        summary["status"] = month_status.get("status") or "open"
        summary["can_edit"] = bool(month_status.get("canEdit", month_status.get("can_edit", True)))
        summary["payroll"] = month_status.get("payroll") or {}
        return summary

    @server.tool()
    async def hr_month_overview(
        period_key: str,
        include_entries: bool = False,
    ) -> dict[str, Any]:
        """Build a BuchhaltIQ HR month overview for employees, hours and absences.

        This is the high-level tool Claude should use for questions like
        "who worked how often in April?" or "is payroll ready for this month?".
        """
        _validate_period_key(period_key)

        if config.mode is Mode.DEMO:
            employees = load_hr_employees()
            entries = _filter_entries_for_period(load_hr_time_entries(), period_key=period_key)
            absences = _filter_absences_for_period(load_hr_absences(), period_key=period_key)
            month_status = _demo_month_status(period_key)
            return _build_month_overview(
                period_key=period_key,
                employees=employees,
                entries=entries,
                absences=absences,
                month_status=month_status,
                include_entries=include_entries,
                source="demo",
            )

        assert client is not None
        employees_payload = await client.list_employees()
        entries_payload = await client.hr_time_entries_for_month(period_key=period_key)
        absences_payload = await client.hr_absences_for_month(period_key=period_key)
        month_status = await client.hr_month_status(period_key=period_key)
        return _build_month_overview(
            period_key=period_key,
            employees=_coerce_rows(employees_payload, "employees"),
            entries=_coerce_rows(entries_payload, "entries"),
            absences=_coerce_rows(absences_payload, "absences"),
            month_status=month_status,
            include_entries=include_entries,
            source="production",
        )
