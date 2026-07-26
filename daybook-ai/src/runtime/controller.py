"""Small local controller server for Daybook AI.

The controller serves a stable browser shell on port 8500. Streamlit runs
separately on port 8501 inside an iframe. During shutdown, the browser is
redirected to a static goodbye page before Streamlit is stopped, preventing
Streamlit's built-in connection-error dialog from appearing.
"""

from __future__ import annotations

import html
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


@dataclass(frozen=True)
class ControllerConfig:
    host: str
    port: int
    streamlit_url: str
    application_name: str = "Daybook AI"


class ControllerState:
    def __init__(self) -> None:
        self.shutdown_requested = threading.Event()
        self.streamlit_ready = threading.Event()


def _page_template(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f5f7fa;
      --panel: #ffffff;
      --text: #18212b;
      --muted: #586575;
      --accent: #0072b2;
      --border: #c9d1d9;
      --success: #007f5f;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0e1117;
        --panel: #161b22;
        --text: #f0f3f6;
        --muted: #a8b3c1;
        --accent: #56b4e9;
        --border: #3a4450;
        --success: #49c89b;
      }}
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      min-height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .center {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 2rem;
    }}
    .panel {{
      width: min(680px, 100%);
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 2rem;
      box-shadow: 0 12px 40px rgba(0,0,0,.12);
    }}
    h1 {{ margin-top: 0; font-size: 2rem; }}
    p {{ line-height: 1.55; }}
    .muted {{ color: var(--muted); }}
    .status {{
      display: flex;
      align-items: center;
      gap: .65rem;
      margin: .85rem 0;
    }}
    .dot {{
      width: .8rem;
      height: .8rem;
      border-radius: 50%;
      background: var(--success);
      flex: 0 0 auto;
    }}
    .spinner {{
      width: 1.2rem;
      height: 1.2rem;
      border: 3px solid var(--border);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin .85s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    iframe {{
      position: fixed;
      inset: 0;
      width: 100%;
      height: 100%;
      border: 0;
      background: var(--bg);
    }}
  </style>
</head>
<body>
{body}
</body>
</html>"""
    return document.encode("utf-8")


def _loading_page(application_name: str) -> bytes:
    safe_name = html.escape(application_name)
    return _page_template(
        f"Starting {safe_name}",
        f"""
<div class="center">
  <main class="panel" aria-live="polite">
    <h1>{safe_name}</h1>
    <div class="status">
      <span class="spinner" aria-hidden="true"></span>
      <strong>Starting the local application…</strong>
    </div>
    <p class="muted">
      Preparing Streamlit and the local language model. This page will update automatically.
    </p>
  </main>
</div>
<script>
  setTimeout(() => window.location.reload(), 800);
</script>
""",
    )


def _application_page(streamlit_url: str, application_name: str) -> bytes:
    safe_url = html.escape(streamlit_url, quote=True)
    safe_name = html.escape(application_name)
    return _page_template(
        safe_name,
        f"""
<iframe
  src="{safe_url}"
  title="{safe_name}"
  allow="clipboard-read; clipboard-write"
></iframe>
""",
    )


def _goodbye_page(application_name: str) -> bytes:
    safe_name = html.escape(application_name)
    return _page_template(
        f"{safe_name} stopped",
        f"""
<div class="center">
  <main class="panel">
    <h1>{safe_name} has shut down</h1>
    <div class="status">
      <span class="dot" aria-hidden="true"></span>
      <strong>Application services stopped safely.</strong>
    </div>
    <p>Streamlit and the local AI server started by {safe_name} have been closed.</p>
    <p class="muted">You may now close this browser tab.</p>
  </main>
</div>
""",
    )


def create_handler(
    config: ControllerConfig,
    state: ControllerState,
) -> type[BaseHTTPRequestHandler]:
    class ControllerRequestHandler(BaseHTTPRequestHandler):
        server_version = "DaybookController/1.0"

        def log_message(self, format: str, *args: object) -> None:
            # Keep the terminal quiet during normal browser polling.
            return

        def _send_html(self, content: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            path = urlparse(self.path).path

            if path == "/health":
                payload = b"ok"
                self.send_response(HTTPStatus.OK.value)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return

            if path == "/shutdown":
                state.shutdown_requested.set()
                self._send_html(_goodbye_page(config.application_name))
                return

            if path == "/goodbye":
                self._send_html(_goodbye_page(config.application_name))
                return

            if path == "/":
                if state.shutdown_requested.is_set():
                    self._send_html(_goodbye_page(config.application_name))
                elif state.streamlit_ready.is_set():
                    self._send_html(
                        _application_page(
                            config.streamlit_url,
                            config.application_name,
                        )
                    )
                else:
                    self._send_html(_loading_page(config.application_name))
                return

            self._send_html(
                _page_template(
                    "Not found",
                    '<div class="center"><main class="panel"><h1>Page not found</h1></main></div>',
                ),
                HTTPStatus.NOT_FOUND,
            )

    return ControllerRequestHandler


class ControllerServer:
    def __init__(self, config: ControllerConfig) -> None:
        self.config = config
        self.state = ControllerState()
        handler = create_handler(config, self.state)
        self._server = ThreadingHTTPServer(
            (config.host, config.port),
            handler,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="daybook-controller",
            daemon=True,
        )

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def mark_streamlit_ready(self) -> None:
        self.state.streamlit_ready.set()

    def wait_for_shutdown(self, timeout: float | None = None) -> bool:
        return self.state.shutdown_requested.wait(timeout)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=3)
