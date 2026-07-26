from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import FrameLocator

from tests.ui.helpers import navigate


def card_for_title(
    app_frame: FrameLocator,
    title: str,
):
    """Find the nearest rendered task card containing the title and action."""
    heading = app_frame.get_by_role(
        "heading",
        name=title,
        exact=True,
    )

    heading.wait_for(
        state="visible",
        timeout=15_000,
    )

    return heading.locator(
        "xpath=ancestor::*[.//button[normalize-space()='Open task']][1]"
    )


@pytest.mark.ui
def test_create_open_edit_complete_and_reopen_task(
    app_frame: FrameLocator,
):
    unique = uuid.uuid4().hex[:8]
    original_title = f"UI test task {unique}"
    edited_title = f"UI edited task {unique}"

    navigate(app_frame, "Tasks")

    app_frame.get_by_text(
        "Create task",
        exact=True,
    ).click()

    app_frame.get_by_label(
        "Title",
        exact=True,
    ).fill(original_title)

    app_frame.get_by_label(
        "Description",
        exact=True,
    ).fill("Created by the Playwright UI test.")

    app_frame.get_by_role(
        "button",
        name="Create task",
        exact=True,
    ).click()

    task_card = card_for_title(
        app_frame,
        original_title,
    )

    task_card.get_by_role(
        "button",
        name="Open task",
        exact=True,
    ).click()

    app_frame.get_by_text(
        "Task details",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )

    title_input = app_frame.get_by_label(
        "Title",
        exact=True,
    )
    title_input.fill(edited_title)

    app_frame.get_by_role(
        "button",
        name="Save changes",
        exact=True,
    ).click()

    app_frame.get_by_role(
        "heading",
        name=edited_title,
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )

    app_frame.get_by_role(
        "button",
        name="Mark complete",
        exact=True,
    ).click()

    navigate(app_frame, "Today")

    completed_heading = app_frame.get_by_role(
        "heading",
        name=edited_title,
        exact=True,
    )

    completed_heading.wait_for(
        state="visible",
        timeout=15_000,
    )

    completed_card = completed_heading.locator(
        "xpath=ancestor::*[.//button[normalize-space()='Reopen']][1]"
    )

    completed_card.get_by_role(
        "button",
        name="Reopen",
        exact=True,
    ).click()

    navigate(app_frame, "Tasks")

    app_frame.get_by_role(
        "heading",
        name=edited_title,
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )


@pytest.mark.ui
def test_open_task_from_today_page(app_frame: FrameLocator):
    navigate(app_frame, "Today")

    open_buttons = app_frame.get_by_role(
        "button",
        name=re.compile(r"open task", re.IGNORECASE),
    )

    if open_buttons.count() == 0:
        pytest.skip("No task cards are available on Today.")

    open_buttons.first.click()

    app_frame.get_by_text(
        "Task details",
        exact=True,
    ).wait_for(
        state="visible",
        timeout=15_000,
    )
