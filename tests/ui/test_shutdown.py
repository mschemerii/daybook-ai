from __future__ import annotations

import pytest
from playwright.sync_api import FrameLocator, Page


@pytest.mark.ui
@pytest.mark.shutdown
def test_shutdown_from_browser(
    page: Page,
    app_frame: FrameLocator,
):
    shutdown = app_frame.get_by_role(
        "link",
        name="Shut down Daybook AI",
    )

    shutdown.click()

    page.get_by_text(
        "Daybook AI has shut down",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )

    page.get_by_text(
        "Application services stopped safely.",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )
