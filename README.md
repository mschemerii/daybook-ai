# Daybook AI

Daybook AI is a compact, local-first task manager and daily journal for working professionals who want to organize responsibilities before focused work. It combines deterministic prioritization with a bounded local language model that may explain, summarize, and propose—but never directly write to the database.

Designed and coded by **Michael Schemer** as an Ethical AI course prototype.

## Features

- Today view with open tasks, due-today tasks, blockers, and three rule-selected focus items.
- Full local task CRUD with provenance.
- Date-based daily journal and previous-entry review.
- Local-model assistant with explicit task/journal access controls.
- User-controlled memory, disabled by default.
- Local audit history that can be inspected and deleted.
- Interactive Ethical AI action-policy examples.
- Limited mode when the model server is offline.
- One-command bootstrapper that detects hardware, downloads missing local-AI components, starts llama.cpp and Streamlit, and opens the default browser.

## Recommended local model

The default model is **`unsloth/Qwen3.5-0.8B-GGUF`**, using:

```text
Qwen3.5-0.8B-UD-Q4_K_XL.gguf
```

The first `python run.py` launch automatically downloads this file from the official Hugging Face repository when the `models/` directory does not already contain a GGUF model. An existing `.gguf` file is never replaced.

Model repository:

```text
https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF
```

Another instruction-tuned GGUF may be used by placing it in `models/` or setting `DAYBOOK_MODEL_PATH` in `.env`.

## Requirements

- Python 3.12+
- Streamlit 1.56.0 (pinned to avoid a confirmed 1.57+ static-file server regression)
- SQLite, included with Python
- llama.cpp with the `llama-server` executable
- A local instruction-tuned GGUF model

## Install Daybook AI

### macOS or Linux

```bash
git clone <your-repository-url> daybook-ai
cd daybook-ai
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python seed_data.py
```

### Windows PowerShell

```powershell
git clone <your-repository-url> daybook-ai
Set-Location daybook-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python seed_data.py
```

## Automatic llama.cpp installation

Manual llama.cpp installation is not required for the normal setup. When `python run.py` cannot find `llama-server`, Daybook AI:

1. Queries the official `ggml-org/llama.cpp` GitHub release API.
2. Selects a prebuilt archive matching Windows, macOS, or Linux, the CPU architecture, and the detected NVIDIA, AMD, Intel, or Apple GPU when a matching build is available.
3. Downloads and safely extracts it into `tools/llama.cpp/`.
4. Uses the project-local executable without changing system directories or the user’s `PATH`.

Official source:

```text
https://github.com/ggml-org/llama.cpp/releases
```

The installer does not replace an existing project-local or system installation. If an accelerated package is unavailable, it selects the best compatible release and the application can fall back to CPU operation.

Internet access is required only for the initial missing-component downloads. Daybook AI does not use internet access for tasks, journals, assistant prompts, analytics, or telemetry.

### Optional manual installation

Manual installation remains supported. Windows users may run `winget install llama.cpp`; macOS users may run `brew install llama.cpp`; Linux users may use an official release archive or build from source. A manually installed `llama-server` on `PATH`, or a path configured with `DAYBOOK_LLAMA_SERVER`, takes precedence over automatic installation.

## GPU detection and backend selection

Run Daybook AI with `python run.py`. The launcher checks only local operating-system information and commands; it does not transmit hardware details or use telemetry.

It detects:

| Detected hardware | Recommended llama.cpp backend | Default GPU layers |
|---|---|---:|
| NVIDIA GPU | CUDA | 99 |
| AMD GPU | Vulkan or ROCm | 99 |
| Intel GPU | Vulkan, SYCL, or OpenVINO | 99 |
| Apple Silicon | Metal | 99 |
| No supported GPU detected | CPU | 0 |

Detection does not install drivers or prove that the installed `llama-server` binary contains the recommended backend. The launcher reports the detected GPU and backend recommendation. If the selected llama.cpp build cannot use that GPU, install the matching official build or set `DAYBOOK_GPU_LAYERS=0` for CPU mode.

Integrated graphics can appear alongside a discrete GPU. The launcher prefers a recognized NVIDIA, AMD, or Intel adapter when the operating system reports more than one device.

## Configure the model

The defaults require no model-path editing. Copy `.env.example` to `.env`; the launcher downloads the default model only when no GGUF is present. The relevant defaults are:

```dotenv
DAYBOOK_DB_PATH=data/daybook.db
DAYBOOK_MODEL_BASE_URL=http://127.0.0.1:8080/v1
DAYBOOK_MODEL_NAME=auto
DAYBOOK_MODEL_PATH=models/Qwen3.5-0.8B-UD-Q4_K_XL.gguf
DAYBOOK_LLAMA_SERVER=llama-server
DAYBOOK_MODEL_HOST=127.0.0.1
DAYBOOK_MODEL_PORT=8080
DAYBOOK_MODEL_CONTEXT_SIZE=4096
DAYBOOK_STREAMLIT_HOST=127.0.0.1
DAYBOOK_STREAMLIT_PORT=8501
```

When the configured file is absent but another `.gguf` already exists in `models/`, the existing model is used and is not overwritten.

`DAYBOOK_LLAMA_SERVER` may be either a command available on `PATH` or an absolute path to the executable.

## Run Daybook AI

Use the project launcher:

```bash
python run.py
```

On Windows:

```powershell
python run.py
```

The launcher performs the following steps:

1. Checks the installed Streamlit version and automatically installs the compatible 1.56.0 release when Streamlit is missing or version 1.57+ is installed.
2. Detects the operating system, CPU architecture, and available Apple, NVIDIA, AMD, or Intel GPU.
3. Uses an explicitly configured or `PATH`-available `llama-server` when it passes executable validation.
4. Otherwise installs the pinned official llama.cpp `b10217` package selected by an explicit platform matrix.
5. Verifies every runtime archive with its publisher-provided SHA-256 digest and records a compatibility manifest plus executable digest.
6. Runs `llama-server --version` and `--list-devices`; GPU layers are enabled only when the intended backend is reported, with CPU fallback otherwise.
7. Uses an existing GGUF model or downloads `Qwen3.5-0.8B-UD-Q4_K_XL.gguf` when none exists.
8. Starts an authenticated llama.cpp server unless a compatible server is already running.
9. Sends a real test request to `/v1/chat/completions` and requires a valid, non-empty completion before reporting AI as verified.
10. Starts Streamlit and the authenticated local browser controller, then opens Daybook AI at `http://127.0.0.1:8500` automatically.
11. Keeps task and journal features available if downloading, starting, or verifying the local model fails.

The first launch may take longer because the model and runtime are downloaded. Progress and any errors are printed in the terminal; partially downloaded files use a `.part` suffix and are removed after a failed transfer.

The normal user does not need the terminal after startup. Select **Shut down** in the Daybook AI header. The browser moves to a stable local goodbye page, then the launcher stops Streamlit and gracefully terminates only the llama.cpp process that it started. An already-running external llama.cpp server is left running. `Ctrl+C` remains available as a development fallback.

### Direct Streamlit command

The recommended command is `python run.py` because it also handles hardware detection and llama.cpp. To start only Streamlit and still request automatic browser opening:

```bash
streamlit run app.py --server.headless false --browser.gatherUsageStats false
```

This direct command does not start llama.cpp or perform GPU detection.

### Verify that the Assistant is using llama.cpp

At startup, the terminal must show a line similar to:

```text
Local AI inference verified. Loaded model: Qwen3.5-0.8B-UD-Q4_K_XL.gguf
```

This is stronger than a simple server health check. Daybook AI first reads `/v1/models`, then sends a small test completion to `/v1/chat/completions`. The Assistant page performs the same verification and displays the loaded model name. Every user message sent from the Assistant page is posted to the local llama.cpp OpenAI-compatible endpoint configured by `DAYBOOK_MODEL_BASE_URL`.

If the inference test fails, the Assistant is shown as unavailable, while Tasks and Daily Journal continue to work.

## Start llama.cpp manually

Manual startup remains available for troubleshooting:

```bash
LLAMA_API_KEY="choose-a-local-secret" llama-server \
  -m models/Qwen3.5-0.8B-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 4096 \
  -ngl 99 \
  --cors-origins localhost \
  --no-cors-credentials \
  --no-webui
```

For CPU-only operation:

```bash
LLAMA_API_KEY="choose-a-local-secret" llama-server \
  -m models/Qwen3.5-0.8B-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 4096 \
  -ngl 0 \
  --cors-origins localhost \
  --no-cors-credentials \
  --no-webui
```

Verify the OpenAI-compatible endpoint:

```bash
curl -H "Authorization: Bearer choose-a-local-secret" http://127.0.0.1:8080/v1/models
```

PowerShell alternative:

```powershell
Invoke-RestMethod -Headers @{Authorization="Bearer choose-a-local-secret"} http://127.0.0.1:8080/v1/models
```

## Run tests

```bash
pytest -q
```

## Ethical safeguards

- Rule-based prioritization is visibly separated from AI explanation.
- The model receives only user-selected, minimized records.
- No cloud calls, telemetry, internet tools, email, calendar, commands, or unrestricted file/database access exist.
- Hardware detection uses local operating-system information only.
- The model cannot write to SQLite.
- AI-requested writes must use a proposal object and require application-side confirmation.
- Persistent memory is off by default and is editable and deletable.
- Audit history is local and deletable.
- No productivity scores, surveillance, peer ranking, or shaming language.

## Troubleshooting

### Automatic llama.cpp installation failed

Check the terminal for the pinned release, selected backend, digest validation, and download error. Confirm that GitHub is reachable. A manual installation can be configured with:

```dotenv
DAYBOOK_LLAMA_SERVER=/absolute/path/to/llama-server
```

Windows example:

```dotenv
DAYBOOK_LLAMA_SERVER=C:\path\to\llama-server.exe
```

### Automatic model download failed

Confirm that Hugging Face is reachable, or manually place a GGUF file in `models/` and set:

```dotenv
DAYBOOK_MODEL_PATH=models/exact-model-filename.gguf
```

### GPU was detected but llama.cpp uses the CPU

The launcher enables GPU layers only when `llama-server --list-devices` reports the expected backend. If driver or executable validation fails, it reports the fallback and uses CPU inference. Windows NVIDIA selects CUDA; Windows AMD selects HIP; Windows Intel selects SYCL; Linux AMD selects ROCm; Linux NVIDIA and Intel select Vulkan; macOS selects the official Metal-enabled package.

### Browser does not open

The launcher prints the local address, normally:

```text
http://127.0.0.1:8500
```

Browser opening can fail in remote shells, containers, or systems without a graphical session. The application remains available at the printed address.

## Limitations

- Single-user local prototype; it has per-launch service tokens but no user-account system or encryption-at-rest layer.
- Small local models may produce weak or invalid answers.
- Unsupported or unavailable acceleration falls back to CPU and may be slower.
- The current UI supports direct user task CRUD. The proposal confirmation service and schema are implemented and tested; a future UI iteration can add structured proposal extraction for additional model-driven write requests.
- No external information is available to the assistant.


## Streamlit compatibility note

Daybook AI pins Streamlit to `1.56.0`. Streamlit 1.57 introduced a new Starlette/Uvicorn server path that can fail while serving frontend assets with `RuntimeError: Response content shorter than Content-Length`. The launcher automatically downgrades an incompatible Streamlit installation before starting the application.

### Runtime reuse and LLM verification

The launcher honors `DAYBOOK_LLAMA_SERVER` first, then a `llama-server` available on `PATH`. Automatically installed executables are reused only when their pinned release, operating system, architecture, backend, asset list, manifest, executable digest, version command, and device inspection all validate. Executables from sibling project folders are never reused. Existing GGUF models may still be reused from a sibling Daybook AI folder to avoid another large model download.

AI availability is confirmed with a real request to `/v1/chat/completions`. Verification succeeds when llama.cpp returns a valid, non-empty completion in either `content` or `reasoning_content`; it does not require the model to repeat an exact phrase. Qwen thinking is disabled where supported so normal assistant responses are returned in the visible content field.

## Browser controller and shutdown

Run the application with:

```bash
python run.py
```

The launcher opens `http://127.0.0.1:8500`. This loopback-only controller displays the
Streamlit interface running on port 8501. Selecting **Shut down** first moves
the browser to a static goodbye page, then stops Streamlit and stops
`llama-server` only when Daybook AI started that process. The shutdown request
requires a fresh per-launch token generated by the launcher.

The application does not require the user to inspect the terminal during
ordinary use.

## Capture implemented UI screenshots

Google Chrome must already be installed. Playwright uses the installed Chrome channel; it does not install a second Chromium browser.

Capture the implemented Streamlit pages in light mode:

```bash
python run.py --screenshots light
```

Capture dark mode:

```bash
python run.py --screenshots dark
```

Capture both themes:

```bash
python run.py --screenshots both
```

Screenshots are written to `docs/screenshots/light/` and `docs/screenshots/dark/`. The screenshot script is part of the project at `scripts/capture_pages.py` and should remain tracked in Git. Generated PNG files are ignored.

## Final implementation checklist

- [x] Today, Tasks, Daily Journal, Assistant, About, and Ethical AI pages
- [x] Clickable task cards and editable task details
- [x] Completed-task visibility and one-click reopening from Today
- [x] Deterministic focus ordering with visible rule explanations
- [x] Local SQLite persistence and sample data
- [x] Local llama.cpp model server with real inference verification
- [x] Recommended `unsloth/Qwen3.5-0.8B-GGUF` model
- [x] Automatic model and llama.cpp bootstrap when missing
- [x] Explicit Apple Metal, Windows CUDA/HIP/SYCL, Linux ROCm/Vulkan, and CPU package selection
- [x] Runtime SHA-256, archive, executable, manifest, and device validation
- [x] Loopback-only services with authenticated llama.cpp and controller shutdown requests
- [x] Explicit task/journal consent and minimized model context
- [x] Local audit history and user-controlled memory
- [x] Confirmation-gated AI write proposals
- [x] Browser controller with user-facing shutdown page
- [x] Light, dark, or both screenshot capture modes
- [x] Offline/limited mode when the model is unavailable
- [x] Automated tests and Python compilation validation
