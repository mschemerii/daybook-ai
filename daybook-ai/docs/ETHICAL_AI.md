# Ethical AI Implementation

## Implemented safeguards

| Principle | Implemented software feature |
|---|---|
| Human autonomy | The assistant has read-only context. Writes use `ProposedAction`; `TaskService` rejects writes that do not require confirmation. External communication and commitment changes are prohibited. |
| Privacy | Tasks, journals, memories, and audit history use local SQLite. The model endpoint is local and configurable. No analytics or telemetry code exists. |
| Transparency | Today labels deterministic selection as application rules. Assistant output is labeled local AI interpretation. Consulted records are displayed. |
| Accountability | Audit records store request, consulted provenance, recommendation, and approval state. Users may delete one record or all records. |
| Data minimization | `ContextService` sends limited fields, caps task/journal counts, omits task descriptions and notes, and truncates journal fields. |
| Meaningful oversight | The model cannot access repositories. Application services alone write. AI-originated write proposals require confirmation and schema validation. |
| User-controlled memory | Retention is unchecked by default. Stored memories can be inspected, edited, and deleted. |
| No surveillance | No time, keystroke, application, productivity-score, or peer-comparison data model or UI exists. |

## Prohibited actions

The bounded design prohibits email, messaging, web browsing, command execution, unrestricted file access, surveillance, automatic deletion of source information, and changing commitments.

## Future goals, not currently implemented

- Encryption-at-rest with user-managed keys.
- Structured proposal extraction and confirmation UI for every supported assistant write request.
- Fine-grained record picker rather than category-level task/journal consent.
- Exportable audit reports and retention schedules.
- Formal accessibility testing and external ethical review.
