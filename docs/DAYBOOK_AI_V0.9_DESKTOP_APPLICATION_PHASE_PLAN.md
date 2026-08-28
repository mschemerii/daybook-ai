# Daybook AI v0.9

## Desktop Application Phase Plan

Revision: Streamlit is no longer a required interface. The target is a local-first desktop application with bounded local AI.

| Item | Detail |
| --- | --- |
| Repository | github.com/mschemerii/daybook-ai |
| Current GitHub main reviewed | 0f23cb311ace02a9270c1cda9c8c6f4816a10469 |
| Desktop framework target | PySide6 / Qt for Python |
| Core principle | Rules determine. AI explains. AI proposes. Humans approve. |

## 1. Revised architecture decision

Daybook AI will transition from a browser-served Streamlit interface to a native desktop interface while preserving the existing Python domain, service, repository, migration, SQLite, llama.cpp, and local GGUF layers. The desktop UI should call Python application services directly rather than introducing an HTTP API solely for local UI communication.

| Item | Detail |
| --- | --- |
| Desktop UI | PySide6 / Qt widgets, dialogs, models, themes, and accessibility properties |
| Application logic | Existing Python services remain authoritative |
| Persistence | Existing SQLite repositories and migrations remain authoritative |
| Local AI | Existing llama.cpp controller/client and Qwen GGUF path remain bounded to explanation/proposal roles |
| Launcher/lifecycle | Existing launcher/controller behavior is adapted to open and close the Qt desktop process cleanly |

Future web rule: if Daybook later gains a web interface, it must be designed for multiple users with integrated authentication/authorization and per-user data isolation. That is a future architecture path and is not part of the v0.9 desktop conversion.

## 2. Branch, pull-request, and approval workflow

Every remaining phase or major desktop subphase uses its own branch and pull request. No phase is merged simply because tests pass; review and explicit approval remain release gates.

- Confirm GitHub main and local working-tree status before creating the phase branch.
- Create the planned local branch from current main before implementation begins.
- Implement only the approved phase scope and run focused plus regression validation.
- Review git status, diff --stat, diff --name-status, and the complete relevant diff before staging.
- Commit and push the branch only after explicit approval.
- Create a pull request from the phase branch into main. The PR description must summarize scope, tests, known limitations, and cleanup impact.
- Review the PR diff and checks. Merge only after explicit approval.
- After merge, verify main and optionally create the planned phase tag if approved.
- Delete the merged branch only after explicit approval and successful post-merge verification.
## 3. Updated remaining roadmap

| Work item | Scope | Branch | PR target | Status |
| --- | --- | --- | --- | --- |
| Phase 8 | Deterministic reports, PDF, CSV ZIP | agent/v0.9-phase8-reporting-exports | main | Next |
| Phase 9A | Desktop foundation and shell | agent/v0.9-phase9a-desktop-foundation | main | Pending |
| Phase 9B | Desktop workflow migration | agent/v0.9-phase9b-desktop-workflows | main | Pending |
| Phase 9C | Desktop cutover, lifecycle, packaging validation | agent/v0.9-phase9c-desktop-cutover | main | Pending |
| Phase 10 | Repository cleanup, documentation, final validation, release prep | chore/v0.9-phase10-desktop-cleanup-release | main | Pending |

## 4. Phase 8 - Reports, PDF, and CSV ZIP export

Objective: complete reporting and export as a UI-independent deterministic subsystem before desktop migration. No LLM calls are permitted in report range calculations, aggregation, PDF generation, CSV generation, or ZIP creation.

- Today, selected daily, weekly, monthly, quarterly, yearly, and custom ranges.
- Sunday-Saturday weeks; calendar and configurable fiscal-year periods; fiscal years labeled by ending year.
- Condensed summary plus detailed actual-entry report; hierarchy, totals, sorting, empty states, and deleted-record exclusion.
- Readable summary/detail PDF output based only on deterministic application data.
- UTF-8 ZIP export containing tasks.csv and time_entries.csv with stable IDs, whole-minute durations, and referential consistency.
- Current-month incomplete tasks with no entries under Current Tasks in Progress when due in the current month.
### Branch and PR gate

- Branch: agent/v0.9-phase8-reporting-exports
- PR: Phase 8 reporting and export -> main
- Merge only after focused reporting/export tests, full non-UI regression, model-unavailable verification, diff review, and explicit approval.
- Suggested approved tag after merge: v0.9-phase8-complete
### Acceptance evidence

- Range and fiscal-boundary tests
- Aggregation and hierarchy tests
- Empty-range and deletion-exclusion tests
- PDF content/render validation
- ZIP membership and CSV schema/reference tests
- UTF-8 tests
- Full non-UI regression plus compileall and git diff --check
## 5. Phase 9A - Desktop foundation and application shell

Objective: introduce PySide6 without removing Streamlit yet. Build a native application shell that proves the desktop architecture, direct service integration, theme system, navigation, and lifecycle behavior before feature migration.

- Add PySide6 as the desktop UI dependency and separate desktop UI code from domain/service/repository code.
- Create a native main window matching the approved dark desktop design: left navigation, dashboard cards, content workspace, status footer, and light/dark appearance support.
- Create desktop application composition/bootstrap code that constructs repositories/services once and injects them into views/controllers.
- Adapt run.py and runtime/controller behavior so launch opens a Qt window rather than requiring a browser for the new path.
- Keep the existing Streamlit app temporarily available as a migration reference and regression oracle; do not delete it in this phase.
- Provide deterministic UI state handling that does not depend on Streamlit reruns or session state.
- Add desktop test infrastructure suitable for headless/unit-level Qt testing and limited end-to-end interaction tests.
### Branch and PR gate

- Branch: agent/v0.9-phase9a-desktop-foundation
- PR: Phase 9A native desktop foundation -> main
- Merge only after the desktop shell launches, closes cleanly, light/dark state persists, core services are reachable, and existing non-UI tests remain green.
- Suggested approved tag after merge: v0.9-phase9a-complete
## 6. Phase 9B - Desktop workflow migration

Objective: migrate all user-facing v0.9 workflows into the native desktop application while preserving existing deterministic and ethical boundaries.

- Today dashboard: deterministic focus ranking/facts, journal snapshot, status cards, and grounded AI explanation/fallback.
- Tasks: create/edit/complete/reopen/delete, estimates, epics/subtasks, ordering, dependencies, named warnings, blocked states, and time-entry behavior.
- AI decomposition: readiness, clarification, proposal generation, editable review, insert/remove/reorder/select, provenance, explicit approval, and idempotent persistence.
- Daily Journal: create/edit/view workflows with existing persistence semantics.
- Reports: on-screen summary/detail views plus PDF and CSV ZIP export from Phase 8 services.
- Assistant, About, Ethical AI, Settings, appearance preferences, local model status/fallback, and shutdown controls.
- Ensure AI-generated interpretation is visually distinct from deterministic facts and cannot imply authoritative ranking or database authority.
- Ensure long-running AI calls do not freeze the Qt event loop; use bounded worker execution while keeping persistence approval on validated application-service paths.
### Branch and PR gate

- Branch: agent/v0.9-phase9b-desktop-workflows
- PR: Phase 9B desktop workflow migration -> main
- Merge only after the full desktop end-to-end workflow passes and model-unavailable fallback leaves deterministic workflows usable.
- Suggested approved tag after merge: v0.9-phase9b-complete
## 7. Phase 9C - Desktop cutover, lifecycle, and packaging validation

Objective: make the native desktop application the authoritative user interface, validate startup/shutdown/resource release, and prepare desktop distribution behavior before removing the legacy UI.

- Switch the documented/default launcher to the PySide6 desktop application.
- Verify llama.cpp startup, loopback behavior, local model detection/download behavior, inference, fallback, and clean model-memory release.
- Verify application close, explicit shutdown, abnormal-error recovery, and repeated launch/close cycles without orphaned processes or locked database state.
- Validate native dialogs, file save/export behavior, keyboard navigation, focus visibility, readable labels, narrow/resized windows, and light/dark appearance.
- Validate macOS desktop behavior first; preserve Windows launcher/install compatibility where current support exists.
- Evaluate desktop packaging (for example PyInstaller) only after the source-run desktop application is stable. Packaging must not become a blocker for functional completion unless explicitly approved as a release requirement.
- Create replacement desktop screenshot/test tooling before retiring browser-specific tooling.
### Branch and PR gate

- Branch: agent/v0.9-phase9c-desktop-cutover
- PR: Phase 9C desktop cutover and lifecycle -> main
- Merge only after the desktop app is the default path and full desktop workflow, shutdown lifecycle, real inference, fallback, and export validation pass.
- Suggested approved tag after merge: v0.9-phase9-complete
## 8. Phase 10 - Repository cleanup, documentation, final validation, and release preparation

Objective: remove obsolete Streamlit-era implementation and test artifacts only after desktop parity is proven, then make the repository accurately represent the native desktop product.

### Cleanup rule

Nothing is deleted merely because it mentions Streamlit. Each candidate must first be checked for imports, runtime references, test coverage replacement, documentation references, installer/launcher dependencies, and any reusable non-UI logic. Reusable logic must be moved or preserved before deletion.

### Likely cleanup candidates to audit

- app.py - currently the large Streamlit application entry point.
- .streamlit/ - Streamlit-specific configuration.
- src/ui/components.py - audit whether it is Streamlit-specific or contains reusable presentation helpers.
- tests/streamlit/ - replace with desktop UI tests before removal.
- UI_TESTING.md - replace with desktop UI testing documentation.
- scripts/run_ui_tests.py and scripts/capture_pages.py - replace or repurpose for Qt desktop testing/screenshot capture.
- requirements.txt Streamlit dependency - remove only after no supported runtime/test path imports Streamlit.
- Launcher/controller code that exists only to start, monitor, or stop Streamlit/browser processes.
- README instructions, screenshots, and examples that describe Streamlit or browser startup as the current UI.
- Any stale sample-data, generated artifact, obsolete test helper, abandoned migration experiment, duplicate documentation, or dead code discovered by reference analysis.
### Required cleanup verification

- Repository-wide reference search for every deleted or renamed file/module.
- Import/compile validation after cleanup.
- No Streamlit dependency remains unless a consciously retained compatibility utility still requires it.
- No browser-only UI tests remain as authoritative desktop acceptance evidence.
- No .db, .gguf, downloaded llama.cpp tools, credentials/.env, exports, runtime-state files, preference files, build output, or packaging artifacts are tracked.
- Fresh install/start/stop behavior is documented and reproduced.
### Documentation and release work

- Rewrite README architecture and screenshots for the desktop UI.
- Document install, start, stop, local database location/behavior, model requirements, fallback, demo seeding, reporting/export, and current limitations.
- Update Ethical AI documentation with Todd May / Decency Principle, Floridi & Cowls principles, and NIST AI RMF conceptual alignment.
- Reconcile automatic first-launch demo seeding with any legacy seed_data.py path so there is one clear sample-data story.
- Run final focused tests, complete non-UI suite, desktop UI suite, shutdown lifecycle, real inference, fallback, migrations, exports, compileall, git diff --check, and repository safety review.
### Branch and PR gate

- Branch: chore/v0.9-phase10-desktop-cleanup-release
- PR: Phase 10 desktop cleanup and release preparation -> main
- The cleanup PR must list every removed file and the replacement/justification for its removal.
- Merge only after complete desktop validation and explicit approval.
- Do not create the final v0.9 tag/release until separately approved after merge and post-merge verification.
## 9. Required desktop end-to-end acceptance workflow

1. Launch Daybook as a desktop window with no browser requirement.
2. Create a task and view deterministic ranking facts.
3. Request an AI explanation and verify grounded/fallback behavior.
4. Create/manage dependencies and inspect named warnings/blocked state.
5. Request decomposition for an eligible task.
6. Review, edit, reorder, insert, select/deselect proposed subtasks.
7. Explicitly approve and verify one atomic epic/subtask result with no duplicate approval writes.
8. Record and manage dated time entries.
9. Open summary/detail reports and export PDF plus CSV ZIP.
10. Use Journal, Assistant, Ethical AI, and Settings paths.
11. Switch appearance and verify persistence.
12. Shut down cleanly and verify the Qt app and Daybook-owned llama.cpp process release resources.
## 10. Current repository observations relevant to the transition

- GitHub main reviewed at commit 0f23cb311ace02a9270c1cda9c8c6f4816a10469.
- The repository currently still has app.py, a .streamlit directory, Streamlit-specific tests, UI_TESTING.md, and browser/UI scripts.
- requirements.txt currently declares streamlit==1.56.0 together with requests and python-dotenv.
- The src tree already separates agent, models, repositories, runtime, services, ui, and utils. That separation should be used to minimize business-logic rewrites during the desktop transition.
- The desktop migration therefore should be a controlled replacement of the presentation/runtime boundary, not a rewrite of the deterministic domain or AI-governance layers.
## 11. Definition of desktop v0.9 complete

Daybook AI v0.9 desktop is complete only when the native PySide6 interface is the default supported UI; all existing v0.9 domain rules and AI-governance boundaries remain enforced; reports/exports are deterministic; all AI-originated persistence still requires explicit human approval; the application remains useful when the model is unavailable; startup/shutdown and model-memory release pass; legacy Streamlit artifacts have either been removed or explicitly justified; documentation matches the validated desktop build; and the final release/tag has been explicitly approved.

## 12. Planning rule going forward

Phase 8 remains the next implementation phase. The desktop redesign does not begin inside Phase 8. After Phase 8 is merged and approved, Phase 9A starts the desktop transition. This prevents reporting logic and UI migration from being mixed into one high-risk change.


---

*Markdown transcription of the approved Daybook AI v0.9 Desktop Application Phase Plan. GitHub `main` remains the implementation source of truth.*
