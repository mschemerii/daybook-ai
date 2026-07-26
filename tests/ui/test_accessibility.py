from __future__ import annotations

import re

import pytest
from playwright.sync_api import FrameLocator


@pytest.mark.ui
def test_primary_navigation_options_are_visible(
    app_frame: FrameLocator,
):
    """Verify the six visible navigation choices, not Streamlit internals."""
    expected = [
        "Today",
        "Tasks",
        "Daily Journal",
        "Assistant",
        "About",
        "Ethical AI",
    ]

    for page_name in expected:
        option = app_frame.locator(
            ".st-key-top_navigation label"
        ).filter(
            has_text=page_name,
        )

        option.wait_for(
            state="visible",
            timeout=15_000,
        )

        assert option.count() == 1


@pytest.mark.ui
def test_shutdown_control_is_visible(
    app_frame: FrameLocator,
):
    """Verify the visible shutdown control without assuming sanitized classes."""
    shutdown = app_frame.get_by_text(
        re.compile(r"Shut down"),
        exact=False,
    ).first

    shutdown.wait_for(
        state="visible",
        timeout=15_000,
    )

    assert shutdown.is_visible()
