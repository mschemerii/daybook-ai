from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from playwright.sync_api import FrameLocator, Page


CONTROLLER_URL = os.getenv(
    "DAYBOOK_TEST_URL",
    "http://127.0.0.1:8500",
)


@pytest.fixture
def controller_url() -> str:
    return CONTROLLER_URL


@pytest.fixture
def app_frame(
    page: Page,
    controller_url: str,
) -> Iterator[FrameLocator]:
    """Open the controller and return the embedded Streamlit frame."""
    page.goto(
        controller_url,
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    iframe = page.locator("iframe")

    try:
        iframe.wait_for(
            state="visible",
            timeout=30_000,
        )
    except Exception as exc:
        raise AssertionError(
            "The Daybook AI controller did not expose the Streamlit "
            f"iframe at {controller_url}. Start the app with "
            "`python run.py` or use `python scripts/run_ui_tests.py`."
        ) from exc

    frame = page.frame_locator("iframe")
    frame.locator(
        '[data-testid="stAppViewContainer"]'
    ).wait_for(
        state="visible",
        timeout=30_000,
    )

    yield frame
