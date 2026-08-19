from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from src.models.entities import (
    ApprovalResult,
    DecompositionProposal,
    ReviewValidation,
    Task,
)
from src.repositories.database import Database
from src.repositories.task_repository import TaskRepository


class ApprovalIntegrityError(RuntimeError):
    """Raised when durable approval records do not form one complete result."""


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

    def get_clarification_answers(self, task_id: int) -> dict[str, str]:
        """Return durable clarification answers for one task or epic."""
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT answers_json
                FROM task_clarification_answers
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return {}
        try:
            value = json.loads(row["answers_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(
                "Persisted clarification answers are unreadable."
            ) from exc
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(answer, str)
            for key, answer in value.items()
        ):
            raise ValueError(
                "Persisted clarification answers have an invalid format."
            )
        return {
            key: answer.strip()
            for key, answer in value.items()
            if answer.strip()
        }

    def save_clarification_answers(
        self,
        task_id: int,
        answers: dict[str, str],
    ) -> dict[str, str]:
        """Insert or update task clarification answers; empty answers clear them."""
        normalized = {
            key: answer.strip()
            for key, answer in answers.items()
            if isinstance(key, str)
            and isinstance(answer, str)
            and answer.strip()
        }
        with self.db.connect() as conn:
            if not normalized:
                conn.execute(
                    "DELETE FROM task_clarification_answers WHERE task_id = ?",
                    (task_id,),
                )
                return {}
            conn.execute(
                """
                INSERT INTO task_clarification_answers(task_id, answers_json)
                VALUES (?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    answers_json = excluded.answers_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    task_id,
                    json.dumps(
                        normalized,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
        return self.get_clarification_answers(task_id)

    def set_status(self, proposal_id: str, status: str) -> DecompositionProposal:
        if status not in {"draft", "approved", "rejected", "cancelled"}:
            raise ValueError("Unsupported proposal status")
        if status == "approved":
            raise ValueError(
                "Approved status is reserved for atomic proposal application."
            )
        if status in {"rejected", "cancelled"}:
            return self.close_draft(proposal_id, status)
        proposal = self.get(proposal_id)
        if proposal.status != "draft":
            raise ValueError("A terminal proposal cannot return to draft status.")
        return proposal

    def update_payload(self, proposal_id: str, payload_json: str) -> DecompositionProposal:
        """Persist review state only while the proposal remains an active draft."""
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE decomposition_proposals
                SET payload_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE proposal_id = ? AND status = 'draft'
                """,
                (payload_json, proposal_id),
            )
            if cursor.rowcount != 1:
                row = conn.execute(
                    "SELECT status FROM decomposition_proposals WHERE proposal_id = ?",
                    (proposal_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"Proposal {proposal_id} not found")
                raise ValueError(
                    f"A {row['status']} proposal cannot be edited as a draft."
                )
        return self.get(proposal_id)

    def close_draft(self, proposal_id: str, status: str) -> DecompositionProposal:
        if status not in {"rejected", "cancelled"}:
            raise ValueError("A draft may only be rejected or cancelled here")
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM decomposition_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Proposal {proposal_id} not found")
            if row["status"] == status:
                return self._from_row(row)
            if row["status"] != "draft":
                raise ValueError(
                    f"A {row['status']} proposal cannot be changed to {status}."
                )
            conn.execute(
                """
                UPDATE decomposition_proposals
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE proposal_id = ? AND status = 'draft'
                """,
                (status, proposal_id),
            )
        return self.get(proposal_id)

    @staticmethod
    def _selected_keys(payload_json: str) -> list[str]:
        try:
            payload = json.loads(payload_json)
            review = payload.get("review")
            if review is None:
                keys = [item["item_key"] for item in payload["subtasks"]]
            else:
                items = sorted(review["items"], key=lambda item: item["display_order"])
                keys = [item["item_key"] for item in items if item["selected"] is True]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ApprovalIntegrityError(
                "The approved proposal has an unreadable persisted review payload."
            ) from exc
        if not keys or len(keys) != len(set(keys)):
            raise ApprovalIntegrityError(
                "The approved proposal has invalid persisted selected item keys."
            )
        return keys

    @classmethod
    def _persisted_result(cls, conn, proposal_row, *, repeated: bool) -> ApprovalResult:
        expected_keys = cls._selected_keys(proposal_row["payload_json"])
        rows = conn.execute(
            """
            SELECT links.item_key, links.task_id, tasks.parent_task_id
            FROM proposal_task_links AS links
            LEFT JOIN tasks ON tasks.id = links.task_id
            WHERE links.proposal_id = ?
            """,
            (proposal_row["proposal_id"],),
        ).fetchall()
        by_key = {row["item_key"]: row for row in rows}
        if (
            len(rows) != len(expected_keys)
            or set(by_key) != set(expected_keys)
            or any(
                row["parent_task_id"] != proposal_row["parent_task_id"]
                for row in rows
            )
        ):
            raise ApprovalIntegrityError(
                "The approved proposal's task links are missing or inconsistent. "
                "No tasks were recreated."
            )
        return ApprovalResult(
            proposal_id=proposal_row["proposal_id"],
            parent_task_id=int(proposal_row["parent_task_id"]),
            item_task_ids=tuple(
                (key, int(by_key[key]["task_id"])) for key in expected_keys
            ),
            repeated=repeated,
        )

    def approve_atomically(
        self,
        proposal_id: str,
        validate: Callable[[Task, str], ReviewValidation],
        *,
        failure_hook: Callable[[str], Any] | None = None,
    ) -> ApprovalResult:
        """Validate and apply one reviewed proposal under a single write lock."""

        def stage(name: str) -> None:
            if failure_hook is not None:
                failure_hook(name)

        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            proposal = conn.execute(
                "SELECT * FROM decomposition_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if proposal is None:
                raise KeyError(f"Proposal {proposal_id} not found")
            if proposal["status"] == "approved":
                return self._persisted_result(conn, proposal, repeated=True)
            if proposal["status"] != "draft":
                raise ValueError(
                    f"A {proposal['status']} proposal cannot be approved."
                )
            if conn.execute(
                "SELECT 1 FROM proposal_task_links WHERE proposal_id = ? LIMIT 1",
                (proposal_id,),
            ).fetchone() is not None:
                raise ApprovalIntegrityError(
                    "A draft proposal already has task links. No application was attempted."
                )

            parent_row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (proposal["parent_task_id"],),
            ).fetchone()
            if parent_row is None:
                raise KeyError("The proposal parent task no longer exists.")
            parent = TaskRepository._row_to_task(parent_row)
            validated = validate(parent, proposal["payload_json"])
            selected = validated.review.selected_items
            stage("validated")

            next_order = int(
                conn.execute(
                    """
                    SELECT COALESCE(MAX(subtask_order), -1) + 1
                    FROM tasks WHERE parent_task_id = ?
                    """,
                    (parent.id,),
                ).fetchone()[0]
            )
            mapping: dict[str, int] = {}
            for offset, item in enumerate(selected):
                task = Task(
                    id=None,
                    title=item.title,
                    description=item.description,
                    priority=item.priority,
                    due_date=item.due_date,
                    status=item.status,
                    source="AI-assisted breakdown",
                    estimated_hours=item.estimated_hours,
                    provenance=item.provenance,
                    completion_criterion=item.completion_criterion,
                )
                mapping[item.item_key] = TaskRepository._insert(
                    conn,
                    task,
                    parent_task_id=int(parent.id),
                    subtask_order=next_order + offset,
                )
                stage("task_created")

            TaskRepository._refresh_task_type(conn, int(parent.id))
            if parent.status == "Completed" and any(
                item.status != "Completed" for item in selected
            ):
                conn.execute(
                    """
                    UPDATE tasks SET status = 'Open', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (parent.id,),
                )
                TaskRepository._reopen_completed_ancestors(conn, int(parent.id))
            stage("hierarchy_created")

            for item in selected:
                for prerequisite_key in item.prerequisite_item_keys:
                    conn.execute(
                        """
                        INSERT INTO task_dependencies(
                            dependent_task_id, prerequisite_task_id
                        ) VALUES (?, ?)
                        """,
                        (mapping[item.item_key], mapping[prerequisite_key]),
                    )
                    stage("dependency_created")

            for item in selected:
                conn.execute(
                    """
                    INSERT INTO proposal_task_links(proposal_id, item_key, task_id)
                    VALUES (?, ?, ?)
                    """,
                    (proposal_id, item.item_key, mapping[item.item_key]),
                )
                stage("link_created")

            cursor = conn.execute(
                """
                UPDATE decomposition_proposals
                SET status = 'approved', updated_at = CURRENT_TIMESTAMP
                WHERE proposal_id = ? AND status = 'draft'
                """,
                (proposal_id,),
            )
            if cursor.rowcount != 1:
                raise ApprovalIntegrityError(
                    "The proposal approval state changed during application."
                )
            stage("status_updated")
            refreshed = conn.execute(
                "SELECT * FROM decomposition_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            return self._persisted_result(conn, refreshed, repeated=False)
