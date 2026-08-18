from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path

from src.ui.components import PRIORITY_META, STATUS_META
from src.utils.dates import format_date, format_datetime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "app.py"
COMPONENTS_FILE = PROJECT_ROOT / "src" / "ui" / "components.py"

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


def _contrast_ratio(
    accent: str,
    background: str,
    text: str,
) -> float:
    def rgb(value: str) -> tuple[float, float, float]:
        return tuple(
            int(value[index:index + 2], 16) / 255
            for index in (1, 3, 5)
        )

    def mix(
        first: tuple[float, float, float],
        second: tuple[float, float, float],
        first_weight: float,
    ) -> tuple[float, float, float]:
        return tuple(
            first_weight * first_channel
            + (1 - first_weight) * second_channel
            for first_channel, second_channel in zip(
                first,
                second,
                strict=True,
            )
        )

    def luminance(color: tuple[float, float, float]) -> float:
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

    accent_rgb = rgb(accent)
    foreground = mix(accent_rgb, rgb(text), 0.60)
    backdrop = mix(accent_rgb, rgb(background), 0.12)
    foreground_luminance = luminance(foreground)
    backdrop_luminance = luminance(backdrop)

    return (
        max(foreground_luminance, backdrop_luminance) + 0.05
    ) / (
        min(foreground_luminance, backdrop_luminance) + 0.05
    )

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

    assert len(date_inputs) >= 3

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
        assert all(keyword.arg != "disabled" for keyword in date_input.keywords)


def test_optional_task_fields_do_not_use_nonresponsive_form_toggles() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert '"Set due date"' not in app_source
    assert '"Set subtask due date"' not in app_source
    assert '"Set subtask estimated duration"' not in app_source


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

    assert "var(--badge-accent) 60%," in app_source
    assert "var(--badge-accent) 12%," in app_source

    for background, text in STREAMLIT_THEMES:
        for accent in BADGE_ACCENTS:
            assert _contrast_ratio(
                accent,
                background,
                text,
            ) >= 4.5

def test_task_card_css_includes_narrow_window_rules() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert '[class*="st-key-task_card_"]' in app_source
    assert "@media (max-width: 640px)" in app_source
    assert "flex-basis:100%" in app_source


def test_phase6_generation_and_phase7_review_have_explicit_boundaries() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert '"Explain with AI"' in app_source
    assert '"Request Breakdown"' in app_source
    assert '"Generate read-only proposal"' in app_source
    assert "Persisted human-review draft" in app_source
    assert '"Approve and create epic tasks"' in app_source
    assert '"Reject proposal"' in app_source
    assert "Final deterministic approval summary" in app_source
    assert "Verify approval result (no duplicates)" in app_source
    assert '"Cancel breakdown"' in app_source
    assert "Untrusted local AI explanation" in app_source
    assert "Deterministic fallback" in app_source

def test_task_estimate_is_directly_optional_and_origin_is_application_controlled() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert '"Set estimated duration"' not in app_source
    assert '"Source or provenance"' not in app_source
    assert 'placeholder="Optional"' in app_source
    assert '"estimated_hours": estimated_hours' in app_source
    assert 'source="User"' in app_source
    assert '"task_flash_message"' in app_source
    assert 'open_task(created_task.id)' in app_source
    assert '"Task origin"' not in app_source


def test_epic_tasks_expose_full_task_navigation_and_ordered_disclosure() -> None:
    app_source = APP_FILE.read_text(encoding="utf-8")
    component_source = COMPONENTS_FILE.read_text(encoding="utf-8")

    assert '"Tasks in this epic"' in app_source
    assert "Next available task:" in app_source
    assert "← Back to epic:" in app_source
    assert "time_entry_service.recorded_minutes(child.id)" in app_source
    assert "task_service.complete_task(child.id)" in app_source
    assert "expanded=is_next" in app_source
    assert '"Approved proposal audit"' in app_source
    assert "Type: {escape(task_type)}" in component_source
    assert "Epic position:" in component_source
    assert "f\"Subtask {task.subtask_order + 1}\"" not in component_source


def test_task_metadata_is_rendered_as_one_html_block() -> None:
    component_source = COMPONENTS_FILE.read_text(encoding="utf-8")

    assert "{\"\".join(badges)}" in component_source
    assert "epic_position_badge" not in component_source


def test_streamlit_toolbar_is_minimal() -> None:
    config = (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(
        encoding="utf-8"
    )

    assert '[client]' in config
    assert 'toolbarMode = "minimal"' in config
