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


def format_datetime(value: date | datetime | str | None) -> str:
    """Format a timestamp as MM-DD-YYYY HH:MM:SS."""
    if value is None:
        return "Unknown time"

    if isinstance(value, datetime):
        return value.strftime("%m-%d-%Y %H:%M:%S")

    if isinstance(value, date):
        return value.strftime("%m-%d-%Y")

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).strftime("%m-%d-%Y %H:%M:%S")
        except ValueError:
            return value

    return str(value)
