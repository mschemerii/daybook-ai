from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path

from src.ui.components import PRIORITY_META, STATUS_META
from src.utils.dates import format_date, format_datetime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "app.py"

BADGE_ACCENTS = (
    "#D55E00",
    "#0072B2",
    "#009E73",
    "#CC79A7",
)
STREAMLIT_THEMES = (
    ("#FFFFFF", "#31333F"),
    ("#0E1117", "#FAFAFA"),
)


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    return tuple(
        int(value[index:index + 2], 16) / 255
        for index in (1, 3, 5)
    )


def _mix_srgb(
    accent: str,
    theme_color: str,
    accent_weight: float,
) -> tuple[float, float, float]:
    accent_rgb = _hex_to_rgb(accent)
    theme_rgb = _hex_to_rgb(theme_color)

    return tuple(
        accent_weight * accent_channel
        + (1 - accent_weight) * theme_channel
        for accent_channel, theme_channel in zip(
            accent_rgb,
            theme_rgb,
            strict=True,
        )
    )


def _relative_luminance(
    color: tuple[float, float, float],
) -> float:
    linear = tuple(
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in color
    )

    return (
        0.2126 * linear[0]
        + 0.7152 * linear[1]
        + 0.0722 * linear[2]
    )


def _contrast_ratio(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
) -> float:
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)

    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)

    return (lighter + 0.05) / (darker + 0.05)


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



def test_badge_colors_meet_wcag_aa_in_light_and_dark_themes() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    for accent in BADGE_ACCENTS:
        assert f"--badge-accent:{accent}" in app_source

    assert (
        "var(--badge-accent) 60%,"
        in app_source
    )
    assert (
        "var(--badge-accent) 12%,"
        in app_source
    )

    for background, text in STREAMLIT_THEMES:
        for accent in BADGE_ACCENTS:
            foreground_color = _mix_srgb(
                accent,
                text,
                0.60,
            )
            background_color = _mix_srgb(
                accent,
                background,
                0.12,
            )

            assert (
                _contrast_ratio(
                    foreground_color,
                    background_color,
                )
                >= 4.5
            )

def test_task_card_css_includes_narrow_window_rules() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert '[class*="st-key-task_card_"]' in app_source
    assert "@media (max-width: 640px)" in app_source
    assert "flex-basis:100%" in app_source
