from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


OUTPUT_ROOT = Path("docs/screenshots")
PAGES = {
    "Today": "01-today.png",
    "Tasks": "02-tasks.png",
    "Daily Journal": "03-daily-journal.png",
    "Assistant": "04-assistant.png",
    "About": "05-about.png",
    "Ethical AI": "06-ethical-ai.png",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Daybook AI pages.")
    parser.add_argument(
        "--theme",
        choices=("light", "dark", "both"),
        default="light",
        help="Theme or themes to capture.",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:88501",
        help="Streamlit URL to capture.",
    )
    return parser.parse_args()


def wait_for_app(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    try:
        page.locator('[data-testid="stAppViewContainer"]').wait_for(
            state="visible",
            timeout=30_000,
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(f"Daybook AI did not become available at {url}.") from exc
    wait_for_rerender(page)


def wait_for_rerender(page: Page) -> None:
    page.wait_for_timeout(900)
    spinner = page.locator('[data-testid="stSpinner"]')
    try:
        spinner.wait_for(state="hidden", timeout=8_000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(350)


def click_navigation(page: Page, label: str) -> None:
    exact = re.compile(rf"^{re.escape(label)}$")
    candidates = [
        page.get_by_role("radio", name=label, exact=True),
        page.locator('[data-testid="stRadio"] label').filter(has_text=exact),
        page.get_by_role("button", name=label, exact=True),
        page.get_by_text(label, exact=True),
    ]
    for locator in candidates:
        try:
            if locator.count() and locator.first.is_visible():
                locator.first.click()
                wait_for_rerender(page)
                return
        except PlaywrightError:
            continue
    raise RuntimeError(f'Could not find navigation control "{label}".')


def save(page: Page, directory: Path, filename: str) -> None:
    destination = directory / filename
    page.screenshot(path=str(destination), full_page=True, animations="disabled")
    print(f"Saved: {destination.resolve()}", flush=True)


def capture_theme(url: str, theme: str) -> int:
    directory = OUTPUT_ROOT / theme
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chrome")
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                device_scale_factor=1,
                color_scheme=theme,
                reduced_motion="reduce",
            )
            page = context.new_page()
            page.set_default_timeout(15_000)
            wait_for_app(page, url)
            for label, filename in PAGES.items():
                print(f"Capturing {theme}: {label}", flush=True)
                click_navigation(page, label)
                save(page, directory, filename)

            click_navigation(page, "Tasks")
            open_button = page.get_by_role(
                "button",
                name=re.compile(r"open task", re.IGNORECASE),
            )
            if open_button.count():
                open_button.first.click()
                wait_for_rerender(page)
                save(page, directory, "07-task-detail.png")
            else:
                print("Skipped task detail: no task was available.", flush=True)

            context.close()
            browser.close()
    except Exception as exc:
        print(f"Screenshot capture failed for {theme}: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    args = parse_arguments()
    themes = ("light", "dark") if args.theme == "both" else (args.theme,)
    result = 0
    for theme in themes:
        result = max(result, capture_theme(args.url, theme))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
