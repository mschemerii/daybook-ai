"""One-command launcher for Daybook AI.

Place this file at the project root:

    daybook-ai-production/run.py
"""

from __future__ import annotations

from src.runtime.launcher import run


if __name__ == "__main__":
    raise SystemExit(run())
