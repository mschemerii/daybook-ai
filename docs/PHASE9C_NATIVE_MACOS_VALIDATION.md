# Phase 9C native macOS validation

Run these checks from the Phase 9C branch in the existing local repository.
They do not require editing files.

## Preparation

```bash
cd ~/Library/CloudStorage/OneDrive-Personal/Maryville/daybook-ai
git status -sb
git branch --show-current
python scripts/preflight.py --verify-deps
```

Confirm the branch is `agent/v0.9-phase9c-desktop-cutover` after the Phase 9C
changes have been pushed or applied locally.

## Native launch and workflows

```bash
./run.sh
```

Confirm that a native Daybook window opens and no browser opens. Exercise Today,
task create/edit/complete/reopen, a dependency, an epic with subtasks, task time,
epic cumulative time, journal save/reload, reports, all three exports, Assistant
explanation and proposal review, Ethical AI controls, keyboard navigation,
visible focus, Light/Dark appearance, and narrow/resized windows.

Save validation exports and screenshots outside the repository, for example:

```bash
python scripts/capture_desktop.py \
  --output-dir ~/Downloads/daybook-phase9c-validation \
  --theme both
```

Close Daybook once with the window control and once with **Settings > Shut down
Daybook AI**. Repeat `./run.sh`, confirm the appearance and saved data, and
perform at least three launch/close cycles in total.

## AI fallback and process ownership

With Daybook closed, temporarily reserve the configured model port:

```bash
python -m http.server 8080 --bind 127.0.0.1
```

In another terminal, run `./run.sh`. Confirm Daybook opens in limited mode and
deterministic workflows remain usable. Close Daybook, then press Control-C in
the server terminal.

Next, start an independently managed llama.cpp server. In the first terminal:

```bash
set -a
source .env
set +a
LLAMA_BIN="$(command -v "${DAYBOOK_LLAMA_SERVER:-llama-server}")"
LLAMA_API_KEY=phase9c-external-test "$LLAMA_BIN" \
  -m "$DAYBOOK_MODEL_PATH" \
  --host 127.0.0.1 \
  --port 8080 \
  -c "${DAYBOOK_MODEL_CONTEXT_SIZE:-4096}" \
  -ngl "${DAYBOOK_GPU_LAYERS:-99}" \
  --no-webui
```

In the second terminal:

```bash
DAYBOOK_MODEL_API_KEY=phase9c-external-test ./run.sh
```

Confirm Daybook uses the server, real Assistant inference works, and closing
Daybook does not stop that independent server. Stop it manually afterward.

For a normal Daybook-owned launch, confirm real inference succeeds, close the
window, and verify no owned process remains:

```bash
pgrep -af llama-server || true
```

## Legacy compatibility and database release

```bash
./run.sh --streamlit
```

Confirm the legacy interface opens in a browser, then use its normal shutdown.

After all Daybook processes are closed, verify SQLite integrity and an exclusive
write lock:

```bash
python - <<'PY'
import os
import sqlite3
from pathlib import Path

path = Path(os.getenv("DAYBOOK_DB_PATH", "data/daybook.db"))
connection = sqlite3.connect(path, timeout=0)
try:
    print("integrity:", connection.execute("PRAGMA integrity_check").fetchone()[0])
    connection.execute("BEGIN EXCLUSIVE")
    connection.execute("ROLLBACK")
    print("exclusive lock: available")
finally:
    connection.close()
PY
```

The validation passes when data survives restart, integrity reports `ok`, the
exclusive lock is available, no Daybook-owned llama.cpp process remains, and an
independently started llama.cpp process survives Daybook shutdown.
