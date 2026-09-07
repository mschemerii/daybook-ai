"""One-command launcher for Daybook AI.

The native PySide6 application is the default. The legacy Streamlit interface
remains available explicitly during the desktop migration.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

DESKTOP_ALIASES = ("--desktop",)
LEGACY_RUNTIME_OPTIONS = ("--status", "--stop", "--screenshots")


def _print_help() -> None:
    print(
        "usage: run.py [--desktop | --streamlit] [legacy options]\n\n"
        "Start Daybook AI's native desktop application.\n\n"
        "options:\n"
        "  --desktop              start the native application (the default)\n"
        "  --streamlit            start the legacy Streamlit interface\n"
        "  --status               report legacy managed-runtime status\n"
        "  --stop                 stop a legacy managed runtime\n"
        "  --screenshots THEME    capture legacy Streamlit screenshots\n"
        "  -h, --help             show this help message"
    )


def _run_desktop() -> int:
    from src.desktop.runtime import run as run_desktop

    return run_desktop()


def _run_legacy(arguments: list[str]) -> int:
    """Run the legacy parser with only its supported arguments."""
    from src.runtime.launcher import run as run_streamlit

    original = sys.argv
    sys.argv = [original[0], *arguments]
    try:
        return run_streamlit()
    finally:
        sys.argv = original


def main(argv: Sequence[str] | None = None) -> int:
    """Select native desktop by default and preserve explicit legacy modes."""
    arguments = list(sys.argv[1:] if argv is None else argv)

    if not arguments or arguments == list(DESKTOP_ALIASES):
        return _run_desktop()

    if arguments in (["-h"], ["--help"]):
        _print_help()
        return 0

    if "--desktop" in arguments:
        print("Desktop mode does not accept additional launcher options.", file=sys.stderr)
        return 2

    if "--streamlit" in arguments:
        legacy_arguments = [item for item in arguments if item != "--streamlit"]
        return _run_legacy(legacy_arguments)

    if any(option in arguments for option in LEGACY_RUNTIME_OPTIONS):
        return _run_legacy(arguments)

    print(
        f"Unknown launcher option: {arguments[0]}. Use --help for available modes.",
        file=sys.stderr,
    )
    return 2


def run() -> int:
    """Preserve the historical module-level launcher entry point."""
    return main()


if __name__ == "__main__":
    raise SystemExit(run())
