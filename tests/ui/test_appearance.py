from __future__ import annotations

import re

import pytest
from playwright.sync_api import FrameLocator


def select_appearance(
    app_frame: FrameLocator,
    label: str,
    theme: str,
) -> None:
    """Select a visible Streamlit appearance label and verify the result."""
    appearance = app_frame.locator(".st-key-sidebar_appearance")
    appearance.wait_for(state="visible", timeout=15_000)

    exact = re.compile(rf"^{re.escape(label)}$")
    visible_label = appearance.locator("label").filter(has_text=exact)
    visible_label.first.wait_for(state="visible", timeout=15_000)
    visible_label.first.click()

    app_frame.locator(
        f'[data-daybook-theme="{theme}"]'
    ).wait_for(
        state="attached",
        timeout=15_000,
    )

    radio = appearance.get_by_role(
        "radio",
        name=label,
        exact=True,
    )
    assert radio.is_checked()


@pytest.mark.ui
def test_sidebar_light_dark_appearance_switch(
    app_frame: FrameLocator,
) -> None:
    select_appearance(app_frame, "Dark", "dark")
    select_appearance(app_frame, "Light", "light")
