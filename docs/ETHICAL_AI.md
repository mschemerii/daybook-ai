# Ethical AI Implementation

> **Rules determine. AI explains. AI proposes. Humans approve.**

## Implemented controls

- Deterministic services remain authoritative for task state, focus rules,
  dependencies, time-entry rules, completion enforcement, reporting, exports,
  and SQLite writes.
- AI explanations are grounded in application-supplied facts and have a
  deterministic fallback.
- AI decomposition is proposal-only. Application code validates the structure,
  and persistence occurs only after explicit human approval.
- The application remains usable when the model is unavailable.
- Task, journal, audit, reporting, and governance data remain local in SQLite.
- The managed model service is loopback-only.
- Daybook terminates llama.cpp only when it started and owns that process.
- The assistant has no unrestricted browser, email, shell, or file-system tools.
- No telemetry, productivity scoring, keystroke surveillance, or peer ranking
  is implemented.

## Todd May — Decency Principle

In the course framing of Todd May's Decency Principle, ordinary moral regard
for other people should remain part of practical action rather than treating
people merely as instruments or obstacles. Daybook's relevant design choice is
to keep the user as the decision-maker: the model may explain and propose, but
consequential persistence remains subject to application rules and explicit
human approval.

This is an ethical design connection, not a claim that the software can prove
or enforce human decency.

## Floridi and Cowls

Daybook aligns conceptually with their five-principle framework:

- **Beneficence:** AI is used for practical assistance rather than unnecessary
  automation.
- **Non-maleficence:** invalid model output is rejected and model failure
  degrades safely.
- **Autonomy:** the user retains approval authority and the application remains
  useful without AI.
- **Justice:** deterministic rules provide consistent application behavior;
  this is not a claim of population-level fairness.
- **Explicability:** deterministic facts are separated from AI wording and
  application code owns persistence/accountability.

## NIST AI RMF conceptual alignment

Daybook is **not NIST-certified** and does not claim full AI RMF
implementation. Its design has conceptual alignment with the AI RMF Core:

- **Govern:** explicit AI authority boundaries and approval requirements.
- **Map:** local-first use, model limits, and failure modes are documented.
- **Measure:** tests exercise grounding, fallback, migrations, lifecycle,
  reporting, and exports.
- **Manage:** invalid AI output is rejected, model failure degrades to limited
  mode, and externally managed llama.cpp processes are preserved.

## Current limitations

- No encryption-at-rest with user-managed keys.
- No external independent ethical audit.
- No formal fairness evaluation across demographic groups.
- Small local models may produce weak or malformed output.
- No certification or compliance claim is made from these framework
  alignments.
