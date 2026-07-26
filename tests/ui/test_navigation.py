from __future__ import annotations

import pytest
from playwright.sync_api import FrameLocator

from tests.ui.helpers import navigate


@pytest.mark.ui
def test_today_page_loads(app_frame: FrameLocator):
    app_frame.get_by_text(
        "Today",
        exact=True,
    ).first.wait_for(
        state="visible",
        timeout=15_000,
    )

    app_frame.get_by_text(
        "Recommended focus",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )


@pytest.mark.ui
@pytest.mark.parametrize(
    ("page_name", "expected_heading"),
    [
        ("Tasks", "Tasks"),
        ("Daily Journal", "Daily Journal"),
        ("Assistant", "Assistant"),
        ("About", "About Daybook AI"),
        ("Ethical AI", "Ethical AI"),
    ],
)
def test_top_navigation(
    app_frame: FrameLocator,
    page_name: str,
    expected_heading: str,
):
    navigate(app_frame, page_name)

    app_frame.get_by_text(
        expected_heading,
        exact=True,
    ).first.wait_for(
        state="visible",
        timeout=15_000,
    )
