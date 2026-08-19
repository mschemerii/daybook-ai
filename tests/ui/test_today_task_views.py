from __future__ import annotations

import pytest
from playwright.sync_api import FrameLocator


@pytest.mark.ui
@pytest.mark.parametrize(
    ("metric_label", "expected_view"),
    [
        ("Open tasks", "Open"),
        ("Due today", "Due today"),
        ("Blockers", "Blocked"),
        ("Completed", "Completed"),
    ],
)
def test_today_summary_metric_opens_matching_task_view(
    app_frame: FrameLocator,
    metric_label: str,
    expected_view: str,
):
    metric_button = app_frame.get_by_role("button").filter(
        has_text=metric_label,
    ).first
    metric_button.click()

    app_frame.get_by_role(
        "heading",
        name="Tasks",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )

    app_frame.get_by_text(
        f"{expected_view} view",
        exact=False,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )
