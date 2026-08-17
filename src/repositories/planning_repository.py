from __future__ import annotations

from datetime import datetime

from src.models.entities import DecompositionProposal
from src.repositories.database import Database


class PlanningRepository:
    """Stores reviewed proposal state without creating tasks."""

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _from_row(row) -> DecompositionProposal:
        return DecompositionProposal(
            proposal_id=row["proposal_id"],
            parent_task_id=row["parent_task_id"],
            payload_json=row["payload_json"],
            fingerprint=row["fingerprint"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def save(self, proposal: DecompositionProposal) -> DecompositionProposal:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO decomposition_proposals(
                    proposal_id, parent_task_id, payload_json, status, fingerprint
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.parent_task_id,
                    proposal.payload_json,
                    proposal.status,
                    proposal.fingerprint,
                ),
            )
        return self.get(proposal.proposal_id)

    def get(self, proposal_id: str) -> DecompositionProposal:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM decomposition_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Proposal {proposal_id} not found")
        return self._from_row(row)

    def find_draft_by_fingerprint(
        self,
        parent_task_id: int,
        fingerprint: str,
    ) -> DecompositionProposal | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM decomposition_proposals
                WHERE parent_task_id = ? AND fingerprint = ? AND status = 'draft'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (parent_task_id, fingerprint),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def set_status(self, proposal_id: str, status: str) -> DecompositionProposal:
        if status not in {"draft", "approved", "rejected", "cancelled"}:
            raise ValueError("Unsupported proposal status")
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE decomposition_proposals
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE proposal_id = ?
                """,
                (status, proposal_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Proposal {proposal_id} not found")
        return self.get(proposal_id)
