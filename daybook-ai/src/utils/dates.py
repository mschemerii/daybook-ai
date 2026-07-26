from __future__ import annotations

from datetime import date, datetime


def format_date(value: date | datetime | str | None) -> str:
    """Format a date for display as MM-DD-YYYY."""
    if value is None:
        return "No due date"

    if isinstance(value, datetime):
        value = value.date()

    if isinstance(value, date):
        return value.strftime("%m-%d-%Y")

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).strftime("%m-%d-%Y")
        except ValueError:
            return value

    return str(value)
