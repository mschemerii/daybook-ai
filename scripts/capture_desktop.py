from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PAGES = (
    ("today", "01-today.png"),
    ("tasks", "02-tasks.png"),
    ("journal", "03-journal.png"),
    ("reports", "04-reports.png"),
    ("assistant", "05-assistant.png"),
    ("ethical-ai", "06-ethical-ai.png"),
    ("about", "07-about.png"),
    ("settings", "08-settings.png"),
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture native Daybook AI validation screenshots."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Destination outside the repository for generated screenshots.",
    )
    parser.add_argument(
        "--theme",
        choices=("light", "dark", "both"),
        default="both",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "daybook.db",
        help="Source database copied to a temporary validation workspace.",
    )
    parser.add_argument(
        "--offscreen",
        action="store_true",
        help="Use Qt's offscreen platform plugin for headless validation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    output_root = args.output_dir.expanduser().resolve()
    if output_root == PROJECT_ROOT or PROJECT_ROOT in output_root.parents:
        raise SystemExit("Screenshot output must be outside the repository.")
    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from src.desktop.application import build_desktop_application
    from src.desktop.composition import DesktopCompositionConfig

    themes = ("Light", "Dark") if args.theme == "both" else (args.theme.title(),)
    output_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="daybook-desktop-capture-") as temporary:
        temporary_root = Path(temporary)
        database_path = temporary_root / "daybook.db"
        source_database = args.database.expanduser().resolve()
        if source_database.exists():
            source = sqlite3.connect(
                source_database.as_uri() + "?mode=ro", uri=True
            )
            try:
                destination = sqlite3.connect(database_path)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
            finally:
                source.close()

        config = DesktopCompositionConfig(
            project_root=PROJECT_ROOT,
            database_path=database_path,
            preferences_path=temporary_root / "preferences.json",
            seed_demo=not database_path.exists(),
            model_base_url="http://127.0.0.1:8080/v1",
            model_name="auto",
            model_api_key="",
        )
        desktop = build_desktop_application(
            PROJECT_ROOT,
            config=config,
            argv=["daybook-desktop-capture"],
        )
        desktop.window.resize(1280, 760)
        desktop.window.show()

        try:
            for theme in themes:
                desktop.appearance.set_appearance(theme)
                theme_dir = output_root / theme.lower()
                theme_dir.mkdir(parents=True, exist_ok=True)
                for destination, filename in PAGES:
                    desktop.window.navigate(destination)
                    desktop.application.processEvents()
                    path = theme_dir / filename
                    if not desktop.window.grab().save(str(path), "PNG"):
                        raise RuntimeError(f"Could not save screenshot: {path}")
                    print(path)
        finally:
            desktop.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
