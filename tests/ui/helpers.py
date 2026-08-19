
from __future__ import annotations

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
    """Click the visible application-navigation radio label."""
    navigation = frame.locator(
        '.st-key-app_navigation [role="radiogroup"]'
    )

    navigation.wait_for(
        state="visible",
        timeout=15_000,
    )

    option = navigation.locator("label").filter(
        has_text=page_name,
    )

    if option.count() != 1:
        raise AssertionError(
            f"Expected one visible navigation option named "
            f"{page_name!r}, found {option.count()}."
        )

    option.click()
    wait_for_streamlit(frame)


def open_first_task(frame: FrameLocator) -> None:
    button = frame.get_by_role(
        "button",
        name="Open task",
        exact=True,
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
