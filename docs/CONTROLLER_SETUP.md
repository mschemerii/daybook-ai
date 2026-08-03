# Controller-based startup and shutdown

Daybook AI uses three loopback-only services:

- Controller: `http://127.0.0.1:8500`
- Streamlit: `http://127.0.0.1:8501`
- llama.cpp: `http://127.0.0.1:8080`

Run normally:

```bash
python run.py
```

The browser opens the controller URL on port 8500. The controller embeds the
Streamlit application and remains available during shutdown.

When the user selects **Shut down**:

1. The browser navigates away from Streamlit to the token-protected `/shutdown` endpoint on port 8500.
2. The controller immediately displays a static goodbye page.
3. The launcher stops Streamlit.
4. The launcher stops llama.cpp only when Daybook AI started it.
5. The goodbye page remains visible briefly, preventing Streamlit's
   connection-error dialog from appearing.

No additional Python dependency is required for the controller because it uses
Python's standard-library HTTP server.

The launcher creates a fresh shutdown token for each run and passes it to the
Streamlit process. Requests without the correct token receive HTTP 403 and do
not trigger shutdown. The controller, Streamlit, and llama.cpp bind only to
loopback addresses; v0.8 rejects non-loopback host configuration.
