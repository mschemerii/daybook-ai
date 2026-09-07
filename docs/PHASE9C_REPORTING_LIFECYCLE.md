# Phase 9C reporting and lifecycle correction

Migration 4 adds completion events and observed blocker intervals. Existing tasks,
time entries and status values are preserved. Legacy completed records appear in
every report under an unknown-date heading; they are never assigned an invented
completion date. Each pending upgrade creates a fresh timestamped SQLite backup.

Tasks and subtasks must have recorded time before completion through repository
create/update paths. Epics still require all children completed and use cumulative
descendant time. Previously closed tasks are not automatically reopened.

Completion events capture the title, estimate and cumulative recorded minutes at
closure. Reports select these events by UTC closure date independently of the work
dates of time entries. Reopening preserves earlier completion events; subsequent
completion adds a new event. Completion rows are snapshots, not totals to sum across
epics and children or repeated closures. Elapsed hours run from creation to closure,
including periods before reopening. Estimate variance is actual minus estimate.

Manual Blocked status and incomplete direct prerequisites produce separate
observed intervals. Overlapping intervals are merged when calculating a task's
blocked minutes. Reasons capture the prerequisite title or manual notes at the
start of an interval. Historic blocker duration before this migration is unknown;
an already-blocked task's measured interval begins at migration and is marked
partial. Epic blocker duration measures the epic's own blockers, not children's.
Observed blocked time is wall-clock time, not proof of causal schedule delay.

The native report and both PDFs include completion rows. CSV ZIP adds
completions.csv when completion rows exist. Period time-entry totals retain their
original semantics. No AI or cloud service participates.

Validation: run the full desktop suite on macOS, then the non-browser suite.
Manually verify a no-time completion is refused, record time and complete the task,
build its completion-month report, export all formats, reopen and close again.
Verify a legacy closed record shows unknown history and remains closed.

Limits: no retrospective reconstruction; no business-calendar delay calculation;
completion snapshots do not retroactively change when time entries are corrected.
Application-layer enforcement does not police out-of-band direct SQL writes.
