# Validation report

## v0.8 pre-commit validation

Validation was performed from branch `agent/v0.8-runtime-integrity`, based on
merge commit `89bb520`.

### Completed checks

- A fresh Python 3.12 temporary environment installed only
  `requirements.txt` and `requirements-test.txt` successfully.
- The complete non-browser suite passed: **72 passed**.
- All Python files compiled successfully with `python -m compileall -q .`.
- `python run.py --help` loaded the launcher and exposed normal startup plus
  `--screenshots light`, `dark`, and `both`.
- Ruff import, undefined-name, upgrade, and correctness checks passed for all
  changed Python files. Existing repository-wide line-length and date-style
  conventions were not changed as part of this release.
- `git diff --check` passed.
- A clean Linux x64 smoke test downloaded the official pinned llama.cpp
  `b10217` CPU archive, verified its published SHA-256 digest, safely extracted
  it, ran `--version` and `--list-devices`, wrote the installation manifest,
  and selected CPU inference with zero GPU layers.
- A second Linux smoke-test run reused the cached executable only after its
  manifest, executable digest, version, and device inspection passed again.
- On the Apple M4 Max development system, the functional/UI Playwright suite
  passed: **18 passed, 2 deselected**.
- After the `MTL0` device-label correction, the Apple M4 Max launcher reported
  `Backend: Metal`, completed real inference, passed the repeated UI and browser
  shutdown suites, and stopped both managed services cleanly.
- A forced automatic-bootstrap test ignored the configured Homebrew executable,
  downloaded the pinned macOS arm64 `b10217` archive, installed its validated
  `llama-server`, confirmed the Metal backend, and selected 99 GPU layers.
- The browser shutdown lifecycle test passed, real inference completed with the
  configured GGUF model, and Streamlit plus the Daybook-owned llama.cpp process
  stopped cleanly.
- The UI run reproduced the previously observed Tornado `WebSocketClosedError`
  when a browser connection closed. It did not fail a test, but remains recorded
  as a browser-disconnection warning rather than being silently ignored.

### Target-system validation status

The isolated Linux validation environment could not download a usable
Playwright browser because the browser CDN returned an empty or truncated
archive. Browser, inference, shutdown, corrected `MTL0` detection, and automatic
macOS arm64 package selection were completed separately on the Apple M4 Max
development system. No target-system checks remain before the v0.8 commit.

No test failure was bypassed, and no assertion was weakened.
