from __future__ import annotations

import json

from src.repositories.database import Database


class GovernanceRepository:
    def __init__(self, db: Database):
        self.db = db

    def add_audit(self, user_request: str, records_consulted: list[dict], recommendation: str, approved_action: bool | None = None) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO audit_history(user_request, records_consulted, recommendation, approved_action) VALUES (?, ?, ?, ?)",
                (user_request, json.dumps(records_consulted), recommendation,
                 None if approved_action is None else int(approved_action)),
            )
            return cur.lastrowid

    def list_audit(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM audit_history ORDER BY id DESC").fetchall()
        return [dict(r) | {"records_consulted": json.loads(r["records_consulted"])} for r in rows]

    def delete_audit(self, audit_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM audit_history WHERE id = ?", (audit_id,))

    def clear_audit(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM audit_history")

    def create_memory(self, content: str) -> int:
        with self.db.connect() as conn:
            cur = conn.execute("INSERT INTO memories(content) VALUES (?)", (content,))
            return cur.lastrowid

    def list_memories(self) -> list[dict]:
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM memories ORDER BY id DESC").fetchall()]

    def update_memory(self, memory_id: int, content: str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE memories SET content=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (content, memory_id))

    def delete_memory(self, memory_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
