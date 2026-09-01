from datetime import date
import pytest

from src.models.reporting import ReportRange
from src.utils.report_ranges import (
    custom_range,
    daily_range,
    default_month_selection,
    monthly_range,
    quarterly_range,
    today_range,
    weekly_range,
    yearly_range,
)


def test_today_and_daily_are_single_inclusive_days():
    day = date(2026, 9, 1)
    assert today_range(day).start_date == day == today_range(day).end_date
    assert daily_range(day).start_date == day == daily_range(day).end_date


def test_week_is_sunday_through_saturday_across_month_boundary():
    result = weekly_range(date(2026, 9, 1))
    assert result.start_date == date(2026, 8, 30)
    assert result.end_date == date(2026, 9, 5)


def test_week_selected_on_sunday_starts_that_day():
    result = weekly_range(date(2026, 8, 30))
    assert result.start_date == date(2026, 8, 30)
    assert result.end_date == date(2026, 9, 5)


def test_month_handles_leap_year_and_default_selection():
    result = monthly_range(date(2028, 2, 14))
    assert result.start_date == date(2028, 2, 1)
    assert result.end_date == date(2028, 2, 29)
    assert default_month_selection(date(2028, 2, 14)) == date(2028, 2, 1)


def test_calendar_quarters_and_years():
    q = quarterly_range(date(2026, 12, 1))
    assert (q.start_date, q.end_date, q.label) == (
        date(2026, 10, 1),
        date(2026, 12, 31),
        'Q4 2026',
    )
    y = yearly_range(date(2026, 5, 1))
    assert (y.start_date, y.end_date, y.label) == (
        date(2026, 1, 1),
        date(2026, 12, 31),
        '2026',
    )


def test_fiscal_year_uses_ending_year_label():
    fy = yearly_range(date(2026, 8, 15), fiscal=True, fiscal_start_month=7)
    assert fy.start_date == date(2026, 7, 1)
    assert fy.end_date == date(2027, 6, 30)
    assert fy.label == 'FY2027'


def test_fiscal_year_boundary_before_start_month():
    fy = yearly_range(date(2026, 6, 30), fiscal=True, fiscal_start_month=7)
    assert fy.start_date == date(2025, 7, 1)
    assert fy.end_date == date(2026, 6, 30)
    assert fy.label == 'FY2026'


def test_fiscal_quarters_cross_calendar_year():
    q1 = quarterly_range(date(2026, 7, 1), fiscal=True, fiscal_start_month=7)
    q3 = quarterly_range(date(2027, 2, 1), fiscal=True, fiscal_start_month=7)
    assert (q1.start_date, q1.end_date, q1.label) == (
        date(2026, 7, 1), date(2026, 9, 30), 'Q1 FY2027'
    )
    assert (q3.start_date, q3.end_date, q3.label) == (
        date(2027, 1, 1), date(2027, 3, 31), 'Q3 FY2027'
    )



def test_fiscal_year_end_handles_leap_day():
    fy = yearly_range(date(2027, 3, 1), fiscal=True, fiscal_start_month=3)
    assert fy.start_date == date(2027, 3, 1)
    assert fy.end_date == date(2028, 2, 29)
    assert fy.label == 'FY2028'

def test_fiscal_start_month_one_matches_calendar_boundaries_with_fy_label():
    fy = yearly_range(date(2026, 4, 1), fiscal=True, fiscal_start_month=1)
    fq = quarterly_range(date(2026, 4, 1), fiscal=True, fiscal_start_month=1)
    assert (fy.start_date, fy.end_date, fy.label) == (
        date(2026, 1, 1), date(2026, 12, 31), 'FY2026'
    )
    assert (fq.start_date, fq.end_date, fq.label) == (
        date(2026, 4, 1), date(2026, 6, 30), 'Q2 FY2026'
    )


def test_custom_range_is_inclusive_and_rejects_reverse_range():
    result = custom_range(date(2026, 8, 31), date(2026, 9, 1))
    assert result.start_date == date(2026, 8, 31)
    assert result.end_date == date(2026, 9, 1)
    with pytest.raises(ValueError):
        custom_range(date(2026, 9, 2), date(2026, 9, 1))


@pytest.mark.parametrize('month', [0, 13, True, 1.5, '7'])
def test_invalid_fiscal_start_month_fails_loudly(month):
    with pytest.raises(ValueError):
        yearly_range(date(2026, 8, 1), fiscal=True, fiscal_start_month=month)


def test_unknown_range_kind_fails_loudly():
    with pytest.raises(ValueError, match='Unknown report range kind'):
        ReportRange('fortnightly', date(2026, 9, 1), date(2026, 9, 14), 'invalid')
