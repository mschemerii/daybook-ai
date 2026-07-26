from __future__ import annotations

import pytest
from playwright.sync_api import FrameLocator

from tests.ui.helpers import navigate


@pytest.mark.ui
def test_assistant_page_shows_local_data_controls(
    app_frame: FrameLocator,
):
    navigate(app_frame, "Assistant")

    app_frame.get_by_text(
        "Allow access to selected task fields",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )

    app_frame.get_by_text(
        "Allow access to recent journal fields",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )

    app_frame.get_by_text(
        "Save assistant memory",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )


@pytest.mark.ui
@pytest.mark.llm
def test_assistant_reaches_local_llm(
    app_frame: FrameLocator,
):
    navigate(app_frame, "Assistant")

    prompt = "Reply with one short sentence confirming the local model works."

    app_frame.get_by_label(
        "Ask Daybook AI",
        exact=True,
    ).fill(prompt)

    app_frame.get_by_role(
        "button",
        name="Send to local model",
        exact=True,
    ).click()

    app_frame.get_by_text(
        "Local AI interpretation",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=60_000,
    )

    app_frame.get_by_text(
        "Records consulted",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )
