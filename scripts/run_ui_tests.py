from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_URL = "http://127.0.0.1:8500"
STREAMLIT_URL = "http://127.0.0.1:8501"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start an isolated Daybook AI instance and run "
            "programmatic UI tests."
        ),
    )

    parser.add_argument(
        "--include-llm",
        action="store_true",
        help="Include the real local-LLM browser test.",
    )

    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chrome while Playwright runs.",
    )

    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Leave Daybook AI running after the tests.",
    )

    return parser.parse_args()


def url_ready(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(
            url,
            timeout=timeout,
        ) as response:
            return 200 <= response.status < 500
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ):
        return False


def wait_for_url(
    url: str,
    process: subprocess.Popen[str],
    timeout_seconds: int = 120,
) -> None:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "Daybook AI exited before the controller became ready."
            )

        if url_ready(url):
            return

        time.sleep(0.5)

    raise TimeoutError(
        f"Daybook AI did not become ready at {url}."
    )


def request_shutdown(token: str) -> None:
    try:
        urllib.request.urlopen(
            f"{CONTROLLER_URL}/shutdown?token={token}",
            timeout=5,
        ).read()
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ):
        pass


def main() -> int:
    args = parse_arguments()

    if url_ready(CONTROLLER_URL) or url_ready(STREAMLIT_URL):
        print(
            "Daybook AI is already using port 8500 or 8501. "
            "Run `python run.py --stop` before the UI test suite.",
            file=sys.stderr,
        )
        return 2

    with tempfile.TemporaryDirectory(
        prefix="daybook-ui-tests-"
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        test_database = temporary_root / "daybook.db"

        source_database = (
            PROJECT_ROOT
            / "data"
            / "daybook.db"
        )

        if source_database.exists():
            shutil.copy2(
                source_database,
                test_database,
            )

        environment = os.environ.copy()
        controller_token = secrets.token_urlsafe(32)
        environment["DAYBOOK_DB_PATH"] = str(test_database)
        environment["DAYBOOK_TEST_URL"] = CONTROLLER_URL
        environment["DAYBOOK_CONTROLLER_TOKEN"] = controller_token

        print("Starting isolated Daybook AI test instance...")

        application = subprocess.Popen(
            [
                sys.executable,
                "run.py",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            text=True,
        )

        try:
            wait_for_url(
                CONTROLLER_URL,
                application,
            )

            pytest_command = [
                sys.executable,
                "-m",
                "pytest",
                "tests/streamlit",
                "tests/ui",
                "-v",
                "-m",
            ]

            marker_expression = (
                "not shutdown"
                if args.include_llm
                else "not shutdown and not llm"
            )

            pytest_command.append(marker_expression)

            if args.headed:
                pytest_command.append("--headed")

            print(
                "Running functional UI tests...",
                flush=True,
            )

            result = subprocess.run(
                pytest_command,
                cwd=PROJECT_ROOT,
                env=environment,
                check=False,
            )

            if result.returncode != 0:
                return result.returncode

            print(
                "Running shutdown lifecycle test...",
                flush=True,
            )

            shutdown_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/ui/test_shutdown.py",
                    "-v",
                    "-m",
                    "shutdown",
                ]
                + (["--headed"] if args.headed else []),
                cwd=PROJECT_ROOT,
                env=environment,
                check=False,
            )

            return shutdown_result.returncode

        finally:
            if not args.keep_running:
                request_shutdown(controller_token)

                try:
                    application.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    application.terminate()

                    try:
                        application.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        application.kill()


if __name__ == "__main__":
    raise SystemExit(main())
