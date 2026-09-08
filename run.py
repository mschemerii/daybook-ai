"""One-command native launcher for Daybook AI."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def _print_help() -> None:
    print(
        "usage: run.py [--desktop]\n\n"
        "Start Daybook AI's native PySide6 desktop application.\n\n"
        "options:\n"
        "  --desktop    explicit alias for the default native application\n"
        "  -h, --help   show this help message"
    )


def _run_desktop() -> int:
    from src.desktop.runtime import run as run_desktop

    return run_desktop()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    if not arguments or arguments == ["--desktop"]:
        return _run_desktop()
    if arguments in (["-h"], ["--help"]):
        _print_help()
        return 0
    if "--desktop" in arguments:
        print("Desktop mode does not accept additional launcher options.", file=sys.stderr)
        return 2

    print(
        f"Unknown launcher option: {arguments[0]}. Use --help for available modes.",
        file=sys.stderr,
    )
    return 2


def run() -> int:
    return main()


if __name__ == "__main__":
    raise SystemExit(run())
