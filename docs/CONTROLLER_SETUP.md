# Controller-based startup and shutdown

Daybook AI now uses three local services:

- Controller: `http://127.0.0.1:88500`
- Streamlit: `http://127.0.0.1:88501`
- llama.cpp: `http://127.0.0.1:88080`

Run normally:

```bash
python run.py
```

The browser opens the controller URL on port 88500. The controller embeds the
Streamlit application and remains available during shutdown.

When the user selects **Shut down**:

1. The browser navigates away from Streamlit to `/shutdown` on port 88500.
2. The controller immediately displays a static goodbye page.
3. The launcher stops Streamlit.
4. The launcher stops llama.cpp only when Daybook AI started it.
5. The goodbye page remains visible briefly, preventing Streamlit's
   connection-error dialog from appearing.

No additional Python dependency is required for the controller because it uses
Python's standard-library HTTP server.
