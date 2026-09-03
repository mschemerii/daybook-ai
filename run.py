"""One-command launcher for Daybook AI.

The existing Streamlit runtime remains the default during the desktop
migration. Phase 9A adds ``--desktop`` as the native PySide6 launch path.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Dispatch to the legacy or Phase 9A desktop runtime."""
    if "--desktop" in sys.argv[1:]:
        remaining = [argument for argument in sys.argv[1:] if argument != "--desktop"]
        if remaining:
            print(
                "Desktop mode does not accept additional launcher options in Phase 9A.",
                file=sys.stderr,
            )
            return 2
        from src.desktop.runtime import run as run_desktop

        return run_desktop()

    from src.runtime.launcher import run as run_streamlit

    return run_streamlit()


def run() -> int:
    """Preserve the historical module-level launcher entry point."""
    return main()


if __name__ == "__main__":
    raise SystemExit(run())
