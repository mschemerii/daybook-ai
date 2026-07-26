# Future Roadmap

Daybook AI intentionally contains one bounded assistant. Possible future modules include a planning specialist, journal summarizer, blocker-review assistant, meeting-note importer, and privacy/audit reviewer. Each should remain permission-scoped and should communicate through explicit typed requests rather than unrestricted shared access.

A future multi-agent architecture could place a small orchestrator above these specialists, with policy enforcement, provenance, confirmation gates, and a shared local audit layer. Agents would receive least-privilege read tools and return recommendations or proposed actions.

Multi-agent functionality is outside the current prototype. The present project does not dynamically create agents, delegate autonomously, communicate externally, or permit any model to write directly to application data.
