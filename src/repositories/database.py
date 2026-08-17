from __future__ import annotations

import sqlite3
from pathlib import Path

from src.repositories.migrations import migrate


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.backup_path: Path | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        conn = self.connect()
        try:
            self.backup_path = migrate(conn, self.path)
        finally:
            conn.close()
