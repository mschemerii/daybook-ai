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
2. Uses an existing GGUF model or downloads `Qwen3.5-0.8B-UD-Q4_K_XL.gguf` when none exists.
3. Uses an existing `llama-server` or downloads an official compatible llama.cpp release into `tools/llama.cpp/`.
4. Selects GPU offload when supported, or CPU fallback otherwise.
5. Starts llama.cpp unless a compatible server is already running.
6. Discovers the model ID reported by `/v1/models`.
7. Sends a real test request to `/v1/chat/completions` and requires the expected `DAYBOOK_READY` response before reporting AI as verified.
8. Starts Streamlit and opens Daybook AI in the default browser automatically.
9. Keeps task and journal features available if downloading, starting, or verifying the local model fails.

The first launch may take longer because the model and runtime are downloaded. Progress and any errors are printed in the terminal; partially downloaded files use a `.part` suffix and are removed after a failed transfer.

Press `Ctrl+C` once in the launcher terminal. The launcher isolates child processes from the terminal interrupt, stops Streamlit first, then gracefully terminates only the llama.cpp process that it started. An already-running external llama.cpp server is left running.

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
llama-server \
  -m models/Qwen3.5-0.8B-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 4096 \
  -ngl 99
```

For CPU-only operation:

```bash
llama-server \
  -m models/Qwen3.5-0.8B-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 4096 \
  -ngl 0
```

Verify the OpenAI-compatible endpoint:

```bash
curl http://127.0.0.1:8080/v1/models
```

PowerShell alternative:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/v1/models
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

Check the terminal for the selected release and download error. Confirm that GitHub is reachable. A manual installation can be configured with:

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

The installed binary may not include the appropriate backend. Install a CUDA build for NVIDIA, a Vulkan or ROCm build for AMD, a Vulkan/SYCL/OpenVINO build for Intel, or a Metal-enabled macOS build. The official llama.cpp startup log is the source of truth for the backend actually being used.

### Browser does not open

The launcher prints the local address, normally:

```text
http://127.0.0.1:8501
```

Browser opening can fail in remote shells, containers, or systems without a graphical session. The application remains available at the printed address.

## Limitations

- Single-user local prototype; no authentication or encryption-at-rest layer.
- Small local models may produce weak or invalid answers.
- Hardware detection is advisory and cannot guarantee driver or binary-backend compatibility.
- The current UI supports direct user task CRUD. The proposal confirmation service and schema are implemented and tested; a future UI iteration can add structured proposal extraction for additional model-driven write requests.
- No external information is available to the assistant.


## Streamlit compatibility note

Daybook AI pins Streamlit to `1.56.0`. Streamlit 1.57 introduced a new Starlette/Uvicorn server path that can fail while serving frontend assets with `RuntimeError: Response content shorter than Content-Length`. The launcher automatically downgrades an incompatible Streamlit installation before starting the application.

### Runtime reuse and LLM verification

The launcher searches the current project recursively for `.gguf` files and `llama-server`. It also checks sibling folders whose names begin with `daybook-ai`, allowing a newly extracted project version to reuse previously downloaded model and llama.cpp files.

AI availability is confirmed with a real request to `/v1/chat/completions`. Verification succeeds when llama.cpp returns a valid, non-empty completion in either `content` or `reasoning_content`; it does not require the model to repeat an exact phrase. Qwen thinking is disabled where supported so normal assistant responses are returned in the visible content field.

## Browser controller and shutdown

Run the application with:

```bash
python run.py
```

The launcher opens `http://127.0.0.1:8500`. This local controller displays the
Streamlit interface running on port 8501. Selecting **Shut down** first moves
the browser to a static goodbye page, then stops Streamlit and stops
`llama-server` only when Daybook AI started that process.

The application does not require the user to inspect the terminal during
ordinary use.
