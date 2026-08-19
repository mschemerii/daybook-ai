#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

ASSUME_YES=0
NO_LAUNCH=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y) ASSUME_YES=1 ;;
        --no-launch) NO_LAUNCH=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

confirm() {
    local prompt="$1"
    if [ "$ASSUME_YES" -eq 1 ]; then
        return 0
    fi
    printf '%s [y/N] ' "$prompt"
    local reply=""
    IFS= read -r reply || true
    case "$reply" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

python_compatible() {
    "$@" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1
}

find_system_python() {
    local candidate
    for candidate in python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && python_compatible "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    if [ -x "$HOME/.local/bin/uv" ]; then
        printf '%s\n' "$HOME/.local/bin/uv"
        return 0
    fi
    return 1
}

ensure_uv() {
    local uv_path=""
    if uv_path="$(find_uv)"; then
        printf '%s\n' "$uv_path"
        return 0
    fi

    if ! confirm "No usable Python environment is available. Install Astral uv so Daybook can install a managed Python 3.12 runtime?"; then
        die "The validated Daybook AI runtime requires Python 3.12.x."
    fi

    say "Installing uv from Astral's official installer..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
    else
        die "curl or wget is required to install uv automatically. Install Python 3.12+ manually and rerun this installer."
    fi

    uv_path="$(find_uv || true)"
    [ -n "$uv_path" ] || die "uv was installed but its executable could not be located."
    printf '%s\n' "$uv_path"
}

create_venv_with_uv() {
    local uv_path="$1"
    say "Creating .venv with managed Python 3.12 (downloaded only if necessary)..."
    "$uv_path" venv "$ROOT/.venv" --python 3.12
}

[ -f "$ROOT/run.py" ] || die "run.py was not found. Run this installer from an extracted/cloned Daybook AI repository."
[ -f "$ROOT/requirements.txt" ] || die "requirements.txt was not found."
[ -f "$ROOT/scripts/preflight.py" ] || die "scripts/preflight.py was not found."

say "Daybook AI installer"
say "Project: $ROOT"
if [ -d "$ROOT/.git" ]; then
    say "Source: Git clone"
else
    say "Source: extracted folder / GitHub ZIP"
fi
say ""

VENV_PY="$ROOT/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
    if python_compatible "$VENV_PY"; then
        say "Using existing compatible .venv."
    else
        warn "Existing .venv uses an incompatible Python interpreter."
        if confirm "Remove and recreate .venv?"; then
            rm -rf "$ROOT/.venv"
        else
            die "Cannot continue with the incompatible .venv."
        fi
    fi
fi

if [ ! -x "$VENV_PY" ]; then
    SYSTEM_PY="$(find_system_python || true)"
    if [ -n "$SYSTEM_PY" ]; then
        say "Compatible Python detected: $($SYSTEM_PY --version 2>&1)"
        say "Creating project virtual environment..."
        if ! "$SYSTEM_PY" -m venv "$ROOT/.venv"; then
            warn "Python's venv module could not create the environment."
            UV_BIN="$(ensure_uv)"
            create_venv_with_uv "$UV_BIN"
        fi
    else
        UV_BIN="$(ensure_uv)"
        create_venv_with_uv "$UV_BIN"
    fi
fi

[ -x "$VENV_PY" ] || die ".venv was not created successfully."

"$VENV_PY" "$ROOT/scripts/preflight.py"

if "$VENV_PY" "$ROOT/scripts/preflight.py" --verify-deps --quiet >/dev/null 2>&1; then
    say "Python dependencies already satisfy requirements.txt."
else
    if ! confirm "Install or update Daybook AI Python dependencies in .venv from requirements.txt?"; then
        die "Daybook AI dependencies are not ready."
    fi
    say "Installing Python dependencies..."
    "$VENV_PY" -m pip install --disable-pip-version-check --upgrade pip
    "$VENV_PY" -m pip install --disable-pip-version-check -r "$ROOT/requirements.txt"
fi

"$VENV_PY" -m pip check
"$VENV_PY" "$ROOT/scripts/preflight.py" --verify-deps

if [ ! -f "$ROOT/.env" ]; then
    [ -f "$ROOT/.env.example" ] || die ".env.example was not found."
    cp "$ROOT/.env.example" "$ROOT/.env"
    say "Created .env from .env.example. Existing .env files are never overwritten."
else
    say "Existing .env preserved."
fi

say ""
say "Environment setup is complete."
say "Activation is not required; Daybook can be launched with .venv/bin/python directly."

if [ "$NO_LAUNCH" -eq 0 ]; then
    if confirm "Launch Daybook AI now? The existing Daybook launcher may download missing llama.cpp/model runtime components on first launch."; then
        exec "$VENV_PY" "$ROOT/run.py"
    fi
fi

say "To launch later: ./run.sh"
