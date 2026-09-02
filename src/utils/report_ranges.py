from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from src.models.reporting import ReportRange


def _validate_fiscal_start_month(month: int) -> int:
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("Fiscal start month must be an integer from 1 through 12.")
    return month


def _month_end(day: date) -> date:
    return date(day.year, day.month, monthrange(day.year, day.month)[1])


def default_month_selection(today: date) -> date:
    return date(today.year, today.month, 1)


def today_range(today: date) -> ReportRange:
    return ReportRange("today", today, today, f"Today - {today.isoformat()}")


def daily_range(selected: date) -> ReportRange:
    return ReportRange("daily", selected, selected, selected.isoformat())


def weekly_range(selected: date) -> ReportRange:
    # Python Monday=0 ... Sunday=6. Convert to days since Sunday.
    days_since_sunday = (selected.weekday() + 1) % 7
    start = selected - timedelta(days=days_since_sunday)
    end = start + timedelta(days=6)
    return ReportRange("weekly", start, end, f"{start.isoformat()} through {end.isoformat()}")


def monthly_range(selected: date) -> ReportRange:
    start = date(selected.year, selected.month, 1)
    end = _month_end(selected)
    return ReportRange("monthly", start, end, selected.strftime("%B %Y"))


def _fiscal_year_bounds(selected: date, fiscal_start_month: int) -> tuple[date, date, int]:
    fiscal_start_month = _validate_fiscal_start_month(fiscal_start_month)
    start_year = selected.year if selected.month >= fiscal_start_month else selected.year - 1
    start = date(start_year, fiscal_start_month, 1)
    end_month = fiscal_start_month - 1 or 12
    end_year = start_year + (1 if fiscal_start_month != 1 else 0)
    end = date(end_year, end_month, monthrange(end_year, end_month)[1])
    return start, end, end.year


def quarterly_range(
    selected: date,
    *,
    fiscal: bool = False,
    fiscal_start_month: int = 1,
) -> ReportRange:
    if not fiscal:
        quarter = ((selected.month - 1) // 3) + 1
        start_month = (quarter - 1) * 3 + 1
        start = date(selected.year, start_month, 1)
        end_month = start_month + 2
        end = date(selected.year, end_month, monthrange(selected.year, end_month)[1])
        return ReportRange(
            "quarterly",
            start,
            end,
            f"Q{quarter} {selected.year}",
            False,
        )

    fy_start, _, fy_label = _fiscal_year_bounds(selected, fiscal_start_month)
    offset_months = (selected.year - fy_start.year) * 12 + selected.month - fy_start.month
    quarter = offset_months // 3 + 1
    quarter_start_offset = (quarter - 1) * 3
    absolute_month = fy_start.month - 1 + quarter_start_offset
    start_year = fy_start.year + absolute_month // 12
    start_month = absolute_month % 12 + 1
    end_absolute = absolute_month + 2
    end_year = fy_start.year + end_absolute // 12
    end_month = end_absolute % 12 + 1
    start = date(start_year, start_month, 1)
    end = date(end_year, end_month, monthrange(end_year, end_month)[1])
    return ReportRange(
        "quarterly",
        start,
        end,
        f"Q{quarter} FY{fy_label}",
        True,
    )


def yearly_range(
    selected: date,
    *,
    fiscal: bool = False,
    fiscal_start_month: int = 1,
) -> ReportRange:
    if not fiscal:
        return ReportRange(
            "yearly",
            date(selected.year, 1, 1),
            date(selected.year, 12, 31),
            str(selected.year),
            False,
        )
    start, end, label = _fiscal_year_bounds(selected, fiscal_start_month)
    return ReportRange("yearly", start, end, f"FY{label}", True)


def custom_range(start: date, end: date) -> ReportRange:
    if not isinstance(start, date) or not isinstance(end, date):
        raise ValueError("Custom report range requires start and end dates.")
    return ReportRange("custom", start, end, f"{start.isoformat()} through {end.isoformat()}")
