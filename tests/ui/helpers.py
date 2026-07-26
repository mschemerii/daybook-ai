from __future__ import annotations

import re
from playwright.sync_api import FrameLocator


def wait_for_streamlit(frame: FrameLocator) -> None:
    frame.locator(
        '[data-testid="stAppViewContainer"]'
    ).wait_for(
        state="visible",
        timeout=30_000,
    )


def navigate(
    frame: FrameLocator,
    page_name: str,
) -> None:
    """Select one item from Daybook AI's top radio navigation."""
    radio = frame.get_by_role(
        "radio",
        name=page_name,
        exact=True,
    )
    radio.check()
    wait_for_streamlit(frame)


def open_first_task(frame: FrameLocator) -> None:
    button = frame.get_by_role(
        "button",
        name=re.compile(r"open task", re.IGNORECASE),
    ).first

    button.wait_for(
        state="visible",
        timeout=15_000,
    )
    button.click()

    frame.get_by_text(
        "Task details",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )
