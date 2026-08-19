from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "docs" / "screenshots"
CONTROLLER_HEALTH_URL = "http://127.0.0.1:8500/health"
DEFAULT_STREAMLIT_URL = "http://127.0.0.1:8501"
MANAGED_CAPTURE_ENV = "DAYBOOK_CAPTURE_MANAGED"

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
        default="both",
        help="Theme or themes to capture.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_STREAMLIT_URL,
        help="Streamlit URL to capture.",
    )
    return parser.parse_args()


def url_ready(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ):
        return False


def capture_url(url: str) -> str:
    """Mark automated capture so temporary theme changes are not saved."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}daybook_capture=1"


def wait_for_rerender(page: Page) -> None:
    page.wait_for_timeout(900)
    spinner = page.locator('[data-testid="stSpinner"]')
    try:
        spinner.wait_for(state="hidden", timeout=8_000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(350)


def wait_for_app(page: Page, url: str) -> None:
    page.goto(
        capture_url(url),
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    try:
        page.locator('[data-testid="stAppViewContainer"]').wait_for(
            state="visible",
            timeout=30_000,
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Daybook AI did not become available at {url}."
        ) from exc
    wait_for_rerender(page)


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


def set_appearance(page: Page, theme: str) -> None:
    label_text = theme.title()
    exact = re.compile(rf"^{re.escape(label_text)}$")

    group = page.locator(".st-key-sidebar_appearance")
    group.wait_for(state="visible", timeout=15_000)

    visible_label = group.locator("label").filter(has_text=exact)
    if not visible_label.count():
        raise RuntimeError(
            f'Could not find the visible appearance option "{label_text}".'
        )

    radio = group.get_by_role("radio", name=label_text, exact=True)

    if not radio.is_checked():
        visible_label.first.click()
        wait_for_rerender(page)

    if not radio.is_checked():
        raise RuntimeError(
            f'Appearance option "{label_text}" did not become selected.'
        )

    page.locator(f'[data-daybook-theme="{theme}"]').wait_for(
        state="attached",
        timeout=15_000,
    )


def save(page: Page, directory: Path, filename: str) -> None:
    destination = directory / filename
    page.screenshot(
        path=str(destination),
        full_page=True,
        animations="disabled",
    )
    print(f"Saved: {destination.resolve()}", flush=True)


def capture_theme(url: str, theme: str) -> int:
    directory = OUTPUT_ROOT / theme
    directory.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                channel="chrome",
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                device_scale_factor=1,
                color_scheme=theme,
                reduced_motion="reduce",
            )
            page = context.new_page()
            page.set_default_timeout(15_000)

            wait_for_app(page, url)
            set_appearance(page, theme)

            for label, filename in PAGES.items():
                print(f"Capturing {theme}: {label}", flush=True)
                click_navigation(page, label)
                save(page, directory, filename)

            click_navigation(page, "Tasks")
            open_button = page.get_by_role(
                "button",
                name="Open task",
                exact=True,
            )
            if open_button.count():
                open_button.first.click()
                wait_for_rerender(page)
                save(page, directory, "07-task-detail.png")
            else:
                print(
                    "Skipped task detail: no task was available.",
                    flush=True,
                )

            context.close()
            browser.close()
    except Exception as exc:
        print(
            f"Screenshot capture failed for {theme}: {exc}",
            file=sys.stderr,
        )
        return 1

    return 0


def capture_requested_themes(url: str, requested_theme: str) -> int:
    themes = (
        ("light", "dark")
        if requested_theme == "both"
        else (requested_theme,)
    )
    result = 0
    for theme in themes:
        result = max(result, capture_theme(url, theme))
    return result


def run_managed_capture(theme: str) -> int:
    environment = os.environ.copy()
    environment[MANAGED_CAPTURE_ENV] = "1"

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "run.py"),
            "--screenshots",
            theme,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
    )
    return completed.returncode


def main() -> int:
    args = parse_arguments()

    # Internal recursive invocation from run.py --screenshots. The launcher
    # owns Streamlit (and any model it started) and will stop those services
    # after this capture returns, so no controller is expected in this mode.
    if os.environ.get(MANAGED_CAPTURE_ENV) == "1":
        return capture_requested_themes(args.url, args.theme)

    controller_ready = url_ready(CONTROLLER_HEALTH_URL)
    streamlit_ready = url_ready(args.url)

    if controller_ready and streamlit_ready:
        print(
            f"Using running Daybook AI application: {args.url}",
            flush=True,
        )
        return capture_requested_themes(args.url, args.theme)

    if controller_ready != streamlit_ready:
        print(
            "Daybook AI is only partially running. Refusing to adopt an "
            "orphaned controller or Streamlit process. Run "
            "`python run.py --stop` for a managed Daybook instance, or stop "
            "the stale process before capturing screenshots.",
            file=sys.stderr,
        )
        return 2

    print(
        "Daybook AI is not running. Starting capture services, capturing "
        "screenshots, and stopping every service started for capture...",
        flush=True,
    )
    return run_managed_capture(args.theme)


if __name__ == "__main__":
    raise SystemExit(main())
