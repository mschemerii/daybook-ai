from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import FrameLocator

from tests.ui.helpers import navigate


@pytest.mark.ui
def test_save_daily_journal_entry(
    app_frame: FrameLocator,
):
    unique = uuid.uuid4().hex[:8]
    completed_text = f"Completed UI test {unique}"
    tomorrow_text = f"Plan UI follow-up {unique}"

    navigate(app_frame, "Daily Journal")

    app_frame.get_by_label(
        "Completed today",
        exact=True,
    ).fill(completed_text)

    app_frame.get_by_label(
        "Plan for tomorrow",
        exact=True,
    ).fill(tomorrow_text)

    app_frame.get_by_role(
        "button",
        name="Save entry",
        exact=True,
    ).click()

    app_frame.get_by_text(
        "Journal entry saved locally.",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )
