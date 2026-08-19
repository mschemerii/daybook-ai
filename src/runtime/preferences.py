from __future__ import annotations

import json
from pathlib import Path


DEFAULT_APPEARANCE = "Light"
VALID_APPEARANCES = ("Light", "Dark")


def load_appearance_preference(path: Path) -> str:
    """Load a saved local appearance, falling back safely to Light."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return DEFAULT_APPEARANCE

    if not isinstance(payload, dict):
        return DEFAULT_APPEARANCE

    appearance = payload.get("appearance")
    if appearance not in VALID_APPEARANCES:
        return DEFAULT_APPEARANCE
    return str(appearance)


def save_appearance_preference(path: Path, appearance: str) -> None:
    """Persist a validated local appearance preference atomically."""
    if appearance not in VALID_APPEARANCES:
        raise ValueError(f"Unsupported appearance: {appearance!r}")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text(
        json.dumps({"appearance": appearance}, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        temporary_path.chmod(0o600)
    except OSError:
        pass

    temporary_path.replace(path)

    try:
        path.chmod(0o600)
    except OSError:
        pass
