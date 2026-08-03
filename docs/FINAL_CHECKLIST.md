# Final implementation checklist

This checklist describes the implemented proof of concept.

- Today page with counts, due work, blockers, deterministic focus recommendations, and completed tasks.
- Task create, view, edit, complete, delete, and reopen functions.
- Daily journal saved and reviewed by date.
- Local assistant using llama.cpp's OpenAI-compatible API.
- Explicit user consent before tasks or journal records enter model context.
- Data-minimized context with provenance shown in the UI.
- Local audit history and user-controlled memory.
- Confirmation-required proposed actions; the model cannot write directly to SQLite.
- No surveillance, productivity score, external communication, command execution, or internet tools.
- Explicit OS, architecture, and backend package selection with verified CPU fallback.
- Pinned llama.cpp `b10217` bootstrap with SHA-256, archive, executable, device, and cache-manifest validation.
- Explicit configuration and system `PATH` take precedence over automatic runtime downloads.
- Loopback-only managed services, authenticated llama.cpp requests, restricted CORS, and disabled llama.cpp Web UI.
- Browser controller with token-protected shutdown that stops only Daybook-owned processes.
- Screenshot capture for light, dark, or both themes.
- Limited mode when local inference is unavailable.
