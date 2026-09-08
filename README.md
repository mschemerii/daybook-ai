# Daybook AI

Daybook AI is a local-first PySide6 desktop task manager and daily journal with
bounded local AI.

> **Rules determine. AI explains. AI proposes. Humans approve.**

## Architecture

- Python 3.12.x
- PySide6 / Qt for Python
- SQLite
- llama.cpp
- default local model: `Qwen3.5-0.8B-UD-Q4_K_XL.gguf`

There is no supported browser UI, web backend, ORM, desktop coordination API,
or agent framework in v0.9.

## Install

### macOS / Linux

```bash
git clone https://github.com/mschemerii/daybook-ai.git
cd daybook-ai
bash install.sh
```

### Windows

```bat
git clone https://github.com/mschemerii/daybook-ai.git
cd daybook-ai
install.bat
```

The installers create or reuse the project `.venv`, preserve an existing
`.env`, install `requirements.txt`, and run preflight checks.

## Start and stop

macOS / Linux:

```bash
./run.sh
```

Windows:

```bat
run.bat
```

Or, from an activated compatible environment:

```bash
python run.py
```

`python run.py --desktop` is an explicit alias.

Close the native window or use the in-app shutdown control. Daybook stops
llama.cpp only when that exact process was started and owned by the current
Daybook run. An independently started server is left running.

## Local AI and fallback

Startup detects hardware, resolves or bootstraps a compatible llama.cpp
runtime, locates or downloads the configured GGUF model, and attempts a real
chat-completion verification.

If local AI is unavailable, deterministic task, journal, time, reporting, and
export functions remain usable.

## SQLite, backups, and migrations

Default database:

```text
data/daybook.db
```

Override it with `DAYBOOK_DB_PATH`.

Database initialization runs the ordered migration sequence. When an existing
database requires migration, the migration layer creates a pre-migration
backup. Existing records are preserved, and unknown legacy completion timing
remains explicitly unknown rather than being invented.

For an extra manual backup, close Daybook and copy the SQLite file before
experimenting.

## Demo data

There is one sample-data implementation path:
`src.repositories.demo_seed.seed_demo_data`. Database initialization may invoke
it when desktop composition enables demo seeding. The old standalone
`seed_data.py` script is not part of v0.9.

## Tasks, epics, dependencies, and time

Daybook supports standard tasks, epics and ordered subtasks, dependencies and
blocking work, deterministic cycle prevention, and dated time entries.

Time is recorded against individual tasks/subtasks. Epic time is cumulative
from descendant entries and is not added again to report-wide totals.

A task cannot be completed without recorded time. Completion snapshots preserve
the estimate and actual effort used for later reporting. Reopen and blocker
history remain available to deterministic reports.

## Reports and exports

Reports use deterministic date ranges and hierarchy-aware aggregation. Exports
include summary/detail PDF and a UTF-8 CSV ZIP with stable task references and
whole-minute durations.

## AI decomposition and Assistant boundaries

The local model may explain deterministic facts and propose task
decomposition. Application code validates proposals. No AI-originated task
structure is persisted until explicit human approval.

The model never writes directly to SQLite.

## Screenshots

Tracked native screenshots are under `docs/screenshots/light/` and
`docs/screenshots/dark/`.

Fresh validation screenshots belong outside the repository:

```bash
python scripts/capture_desktop.py   --output-dir ~/Downloads/daybook-desktop-validation   --theme both
```

## Validation

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/desktop
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m compileall -q run.py src tests scripts
git diff --check
git status -sb
git diff --stat
git diff --name-status
```

See `docs/DESKTOP_VALIDATION.md`.

## Ethical AI

`docs/ETHICAL_AI.md` connects implemented behavior to Todd May's Decency
Principle, Floridi and Cowls' framework, and conceptual NIST AI RMF alignment.
Daybook does not claim certification or safeguards that are not implemented.

## Limitations

- single-user local prototype
- no encryption-at-rest with user-managed keys
- no cloud AI fallback
- small local models can return weak or invalid output
- no cross-platform executable packaging yet
- no external email, calendar, browsing, or shell tools

## Roadmap

- **Phase 10:** cleanup, documentation, validation, release preparation
- **Phase 11:** user-specified UI/report refinements, expanded decomposition,
  and Assistant functionality after requirements are approved
- **Phase 12:** GitHub Actions executable builds and approved GitHub Release
  distribution for macOS, Windows, and Linux

See `docs/FUTURE_ROADMAP.md`.
