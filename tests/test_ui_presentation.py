from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path

from src.ui.components import PRIORITY_META, STATUS_META
from src.utils.dates import format_date, format_datetime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "app.py"


def test_date_formatters_use_month_day_year() -> None:
    assert format_date(date(2026, 7, 26)) == "07-26-2026"
    assert format_date("2026-07-26") == "07-26-2026"
    assert format_datetime(datetime(2026, 7, 26, 14, 5, 9)) == (
        "07-26-2026 14:05:09"
    )
    assert format_datetime("2026-07-26 14:05:09") == (
        "07-26-2026 14:05:09"
    )


def test_every_date_input_uses_month_day_year_format() -> None:
    tree = ast.parse(APP_FILE.read_text(encoding="utf-8"))
    date_inputs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "date_input"
    ]

    assert len(date_inputs) == 3

    for date_input in date_inputs:
        format_keyword = next(
            (
                keyword
                for keyword in date_input.keywords
                if keyword.arg == "format"
            ),
            None,
        )
        assert format_keyword is not None
        assert isinstance(format_keyword.value, ast.Constant)
        assert format_keyword.value.value == "MM-DD-YYYY"


def test_task_metadata_has_one_accessible_mapping() -> None:
    assert PRIORITY_META == {
        "High": ("▲", "priority-high"),
        "Medium": ("◆", "priority-medium"),
        "Low": ("●", "priority-low"),
    }
    assert STATUS_META == {
        "Open": ("○", "status-open"),
        "In Progress": ("◐", "status-progress"),
        "Blocked": ("■", "status-blocked"),
        "Completed": ("✓", "status-completed"),
    }


def test_task_card_css_includes_narrow_window_rules() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert '[class*="st-key-task_card_"]' in app_source
    assert "@media (max-width: 640px)" in app_source
    assert "flex-basis:100%" in app_source
