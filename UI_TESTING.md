# Daybook AI UI testing

This package adds automated UI tests without replacing application source
files.

## Exact placement

Extract this ZIP into the root of the existing Git repository:

```text
daybook-ai/
├── app.py
├── run.py
├── requirements.txt
├── requirements-test.txt       ← added
├── pytest.ini                  ← added
├── UI_TESTING.md               ← added
├── scripts/
│   └── run_ui_tests.py         ← added
└── tests/
    ├── streamlit/
    │   └── test_app_smoke.py   ← added
    └── ui/
        ├── conftest.py         ← added
        ├── helpers.py          ← added
        ├── test_accessibility.py
        ├── test_assistant.py
        ├── test_journal.py
        ├── test_navigation.py
        ├── test_shutdown.py
        └── test_task_workflow.py
```

From the repository root:

```bash
unzip -o ~/Downloads/daybook-ui-tests.zip
```

## Install test dependencies

Activate the same virtual environment used by Daybook AI:

```bash
python -m pip install -r requirements-test.txt
```

The Playwright Python package does not automatically include a browser.

To use the Google Chrome already installed on the computer, no Playwright
Chromium download is required. The pytest-playwright plugin will use its
default Chromium unless a channel is configured. For maximum reliability,
install Playwright Chromium once:

```bash
python -m playwright install chromium
```

On Linux CI systems, use:

```bash
python -m playwright install --with-deps chromium
```

## Recommended one-command test

```bash
python scripts/run_ui_tests.py
```

The runner:

1. Copies the current SQLite database to a temporary test location.
2. Starts `python run.py`.
3. Waits for the controller at `http://127.0.0.1:8500`.
4. Runs Streamlit AppTest checks.
5. Runs Playwright browser tests.
6. Runs shutdown as the final browser test.
7. Stops any test processes it started.
8. Deletes the temporary database.

The real application database is not modified.

## Include the local LLM test

```bash
python scripts/run_ui_tests.py --include-llm
```

This sends one real prompt to the llama.cpp OpenAI-compatible endpoint.

## Watch the browser

```bash
python scripts/run_ui_tests.py --headed
```

Combine options:

```bash
python scripts/run_ui_tests.py --headed --include-llm
```

## Run only Streamlit AppTest checks

```bash
python -m pytest tests/streamlit -v
```

These are fast and do not require Chrome.

## Run browser tests against an already-running application

Start Daybook AI in one terminal:

```bash
python run.py
```

In a second terminal:

```bash
python -m pytest tests/ui -v -m "not shutdown and not llm"
```

Run the LLM browser test separately:

```bash
python -m pytest tests/ui/test_assistant.py -v -m llm
```

Run shutdown last:

```bash
python -m pytest tests/ui/test_shutdown.py -v -m shutdown
```

## Test coverage provided

The included tests cover:

- Initial Today page
- All six navigation destinations
- Task creation
- Opening a task
- Task editing
- Task completion
- Completed-task reopening
- Journal save
- Assistant privacy controls
- Optional real local-model request
- Primary navigation accessibility
- Shutdown control accessibility
- Browser shutdown lifecycle
- Application loading without a Streamlit exception

## Important limitation

No UI suite can prove every possible combination of user input. Keep the
existing repository/service unit tests. The intended stack is:

1. Unit tests for models, repositories, and services
2. Streamlit AppTest for widget-level behavior
3. Playwright for real browser workflows
4. One manual visual review for layout and wording


## Streamlit navigation implementation note

Streamlit 1.56 visually renders horizontal radio choices as clickable labels
while the underlying `<input type="radio">` elements are hidden. The
Playwright helper therefore clicks the visible label inside
`.st-key-top_navigation` instead of calling `.check()` on the hidden input.


## Version 3 selector fixes

- Tests visible navigation labels rather than Streamlit's changing internal radiogroup markup.
- Tests the visible shutdown text rather than sanitized CSS classes.
- Blurs the assistant prompt before checking that the send button is enabled.
- Finds task cards by their heading and nearest action-button ancestor.
