# Daybook AI UI test v4 overlay

Extract this ZIP into the root of the existing Daybook AI repository.

It replaces only:

```text
tests/ui/test_assistant.py
tests/ui/test_task_workflow.py
```

From the repository root:

```bash
unzip -o ~/Downloads/daybook-ui-tests-v4.zip
```

Run the complete suite:

```bash
python scripts/run_ui_tests.py --headed --include-llm
```

Version 4 fixes:

- Removes the invalid `FrameLocator.page` access.
- Polls the assistant button until Streamlit enables it after the prompt loses focus.
- Opens the Create task expander through its `summary` element.
- Avoids the duplicate `Create task` text locator.
