# Desktop Validation

The authoritative UI acceptance path for Daybook AI v0.9 is PySide6.

## Automated validation

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/desktop
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m compileall -q run.py src tests scripts
git diff --check
```

The retired Playwright `tests/ui` suite contained exactly 20 browser cases:
6 navigation cases, 2 accessibility cases, 1 appearance case, 2 Assistant
cases, 1 journal case, 1 shutdown case, 3 task-workflow cases, and 4
Today-summary cases. One Assistant case also carried `llm`; the shutdown case
also carried `shutdown`.

Those cases are removed because the browser UI is no longer a supported product
surface. Replacement coverage is provided by `tests/desktop`, desktop runtime
tests, model-runtime tests, and the deterministic service/repository suites.

## Native macOS validation

Use a real window for checks that cannot be established by Qt offscreen tests:

- launch without a browser
- create/edit/complete/reopen tasks
- reopen a completed task and confirm its earlier completion remains in reports
- PDF and CSV ZIP export
- real local inference and deterministic fallback
- repeated close/restart
- SQLite release after close
- appearance persistence
- independently started llama.cpp remains running after Daybook exits

Capture native validation screenshots outside the repository:

```bash
python scripts/capture_desktop.py   --output-dir ~/Downloads/daybook-desktop-validation   --theme both
```
