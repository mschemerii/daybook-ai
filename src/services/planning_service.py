from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from src.agent.local_llm import (
    DECOMPOSITION_PROMPT_VERSION,
    RANKING_EXPLANATION_PROMPT_VERSION,
    LocalModelClient,
    LocalModelError,
)
from src.models.entities import (
    DecompositionClassification,
    DecompositionProposal,
    ApprovalResult,
    ProposalAdvisory,
    ProposalReview,
    ProposedSubtask,
    RankingFacts,
    ReadinessAssessment,
    ReviewItem,
    ReviewValidation,
    Task,
    ValidatedDecompositionProposal,
)
from src.repositories.planning_repository import PlanningRepository
from src.services.task_service import (
    DESCRIPTION_MAX_LENGTH,
    STANDARD_ESTIMATE_MAX_HOURS,
    TITLE_MAX_LENGTH,
    VALID_PRIORITIES,
    VALID_STATUSES,
    TaskService,
    TaskValidationError,
)

MAX_SUMMARY_LENGTH = 1_000
MAX_ADVISORIES = 5
MAX_ADVISORY_LENGTH = 500
PROPOSAL_TYPE = "task_decomposition"
VALID_ADVISORY_KINDS = {"blocker", "risk", "missing_information", "milestone"}

TOP_LEVEL_FIELDS = {
    "proposal_type",
    "parent_task_id",
    "proposal_id",
    "summary",
    "requires_confirmation",
    "subtasks",
    "advisories",
}
SUBTASK_FIELDS = {
    "item_key",
    "title",
    "description",
    "estimated_hours",
    "priority",
    "suggested_sequence",
    "completion_criterion",
    "due_date",
    "prerequisite_item_keys",
}
ADVISORY_FIELDS = {"kind", "message"}
REVIEW_ITEM_FIELDS = {
    "item_key",
    "title",
    "description",
    "estimated_hours",
    "priority",
    "status",
    "completion_criterion",
    "due_date",
    "prerequisite_item_keys",
    "selected",
    "display_order",
    "origin",
    "original_content",
}

UNSAFE_ACTIONABLE_PATTERNS = (
    r"\b(?:select|insert|update|delete)\b.{0,40}\b(?:from|into|set|where)\b",
    r"\b(?:drop|alter|create|truncate)\s+table\b",
    r"\b(?:exec|execute)\s*\(",
    r"\b(?:subprocess|os\.system|powershell|cmd\.exe)\b",
    r"(?:^|\s)(?:rm\s+-rf|curl\s+|wget\s+)",
    r"\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b",
    r"\b(?:reveal|print|repeat)\s+(?:the\s+)?(?:system|developer)\s+prompt\b",
    r"\b(?:override|bypass)\s+(?:the\s+)?(?:contract|instructions|validation)\b",
)

VAGUE_TITLES = {
    "do the thing",
    "do thing",
    "task",
    "work on it",
    "work on project",
    "project",
    "stuff",
}

READINESS_QUESTIONS = {
    "clear_title": "What clear title should identify this work?",
    "expected_outcome": "What specific outcome or deliverable should this task produce?",
    "definition_of_done": "What must be true for this task to be considered done?",
    "included_scope": "What is included, and what should remain out of scope?",
    "starting_point": "What is already completed, decided, or available?",
    "constraints": "What requirements, tools, standards, limits, or protected components apply? Enter ‘None known’ if none apply.",
}


class Phase6ValidationError(ValueError):
    """Raised when untrusted model output fails the Phase 6 contract."""


class Phase7ValidationError(ValueError):
    """Raised when reviewed application state is not safe to approve."""


@dataclass(frozen=True, slots=True)
class ExplanationResult:
    text: str
    fingerprint: str
    used_ai: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class ProposalResult:
    proposal: ValidatedDecompositionProposal
    fingerprint: str
    reused: bool = False


class PlanningService:
    """Owns AI proposal boundaries and the human review/approval workflow."""

    def __init__(
        self,
        tasks: TaskService,
        proposals: PlanningRepository,
        model: LocalModelClient,
    ):
        self.tasks = tasks
        self.proposals = proposals
        self.model = model
        self._explanation_cache: dict[str, str] = {}

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def explanation_fingerprint(
        self,
        facts: RankingFacts,
        resolved_model: str,
    ) -> str:
        return self._fingerprint(
            {
                "prompt_version": RANKING_EXPLANATION_PROMPT_VERSION,
                "facts": facts.to_dict(),
                "model": self.model.fingerprint_configuration(resolved_model),
                "generation": {"temperature": 0, "max_tokens": 220},
            }
        )

    def explain_with_ai(self, facts: RankingFacts) -> ExplanationResult:
        fallback = facts.deterministic_explanation
        try:
            resolved_model = self.model.model_identity()
            fingerprint = self.explanation_fingerprint(facts, resolved_model)
            cached = self._explanation_cache.get(fingerprint)
            if cached is not None:
                return ExplanationResult(cached, fingerprint, True)
            generated = self.model.explain_ranking(
                facts.to_dict(),
                resolved_model=resolved_model,
            )
            self._validate_grounded_explanation(generated, facts)
            self._explanation_cache[fingerprint] = generated.strip()
            return ExplanationResult(generated.strip(), fingerprint, True)
        except (LocalModelError, Phase6ValidationError) as exc:
            fallback_fingerprint = self._fingerprint(
                {
                    "prompt_version": RANKING_EXPLANATION_PROMPT_VERSION,
                    "facts": facts.to_dict(),
                    "fallback": True,
                }
            )
            return ExplanationResult(
                fallback,
                fallback_fingerprint,
                False,
                "Local AI could not produce a grounded explanation. "
                "The application-rule explanation remains available. "
                f"{exc}",
            )

    @staticmethod
    def _validate_grounded_explanation(text: str, facts: RankingFacts) -> None:
        if not isinstance(text, str) or not text.strip():
            raise Phase6ValidationError("The model returned an empty explanation.")
        value = text.strip()
        if len(value) > 800:
            raise Phase6ValidationError("The model explanation was too long.")
        lowered = value.casefold()
        if "application rules" not in lowered or "calculated" not in lowered:
            raise Phase6ValidationError(
                "The model did not identify the application-rule calculation."
            )
        if "user-assigned" not in lowered or "priority" not in lowered:
            raise Phase6ValidationError(
                "The model did not distinguish user-assigned priority."
            )
        if not facts.incomplete_blockers and re.search(
            r"\b(?:blocked by|blocker|prerequisite|dependency)\b", lowered
        ):
            raise Phase6ValidationError("The model introduced an unsupported blocker.")
        if facts.estimated_hours is None and re.search(
            r"\b(?:estimate|estimated|hours?)\b", lowered
        ):
            raise Phase6ValidationError("The model introduced an unsupported estimate.")
        if facts.due_date is None and re.search(
            r"\b(?:deadline|overdue|due)\b",
            lowered.replace("no due date", ""),
        ):
            raise Phase6ValidationError("The model introduced an unsupported deadline.")
        if re.search(r"\b(?:completed work|work is complete|already finished)\b", lowered):
            raise Phase6ValidationError("The model claimed unsupported completed work.")
        if re.search(
            r"\b(?:the user wants|the user intends|their intent|their goal|progress is|has started|is working on)\b",
            lowered,
        ):
            raise Phase6ValidationError("The model introduced unsupported intent or progress.")
        if facts.incomplete_blockers and re.search(
            r"\b(?:blocked by|blocker|prerequisite|dependency)\b", lowered
        ) and not any(blocker.casefold() in lowered for blocker in facts.incomplete_blockers):
            raise Phase6ValidationError("The model did not use a supplied blocker identity.")
        allowed_numbers = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(facts.to_dict())))
        output_numbers = set(re.findall(r"\d+(?:\.\d+)?", value))
        if not output_numbers.issubset(allowed_numbers):
            raise Phase6ValidationError("The model introduced an unsupported number or date.")

    @staticmethod
    def classify(task: Task) -> DecompositionClassification:
        if task.task_type == "epic":
            return DecompositionClassification(
                "strong_candidate",
                "This task is already an epic.",
                bool(task.estimated_hours is not None and task.estimated_hours >= 40),
            )
        estimate = task.estimated_hours
        if estimate is None:
            return DecompositionClassification(
                "not_candidate",
                "No estimate is available. A manual breakdown may still be requested.",
            )
        if estimate >= 8:
            return DecompositionClassification(
                "strong_candidate",
                f"The application estimate is {estimate:g} hours, at least 8 hours.",
                estimate >= 40,
            )
        if estimate >= 4:
            return DecompositionClassification(
                "possible_candidate",
                f"The application estimate is {estimate:g} hours, between 4 and 8 hours.",
            )
        return DecompositionClassification(
            "not_candidate",
            f"The application estimate is {estimate:g} hours, below 4 hours.",
        )

    @staticmethod
    def readiness(
        task: Task,
        clarification_answers: dict[str, str] | None = None,
    ) -> ReadinessAssessment:
        answers = {
            key: value.strip()
            for key, value in (clarification_answers or {}).items()
            if isinstance(value, str) and value.strip()
        }
        normalized_title = " ".join(task.title.casefold().split())
        missing: list[str] = []
        if normalized_title in VAGUE_TITLES and not answers.get("clear_title"):
            missing.append("clear_title")
        if not task.description.strip() and not answers.get("expected_outcome"):
            missing.append("expected_outcome")
        if not task.completion_criterion.strip() and not answers.get(
            "definition_of_done"
        ):
            missing.append("definition_of_done")
        if not task.description.strip() and not answers.get("included_scope"):
            missing.append("included_scope")
        if not task.notes.strip() and not answers.get("starting_point"):
            missing.append("starting_point")
        if not task.notes.strip() and not answers.get("constraints"):
            missing.append("constraints")
        return ReadinessAssessment(
            not missing,
            tuple(missing),
            tuple((key, READINESS_QUESTIONS[key]) for key in missing),
        )

    def minimized_task_context(
        self,
        task: Task,
        clarification_answers: dict[str, str],
    ) -> dict[str, Any]:
        prerequisites = [
            f"{item.title} (task {item.id})"
            for item in self.tasks.prerequisites(int(task.id))
        ]
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "user_priority": task.priority,
            "status": task.status,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "estimated_hours": task.estimated_hours,
            "task_type": task.task_type,
            "completion_criterion": task.completion_criterion,
            "planning_notes": task.notes,
            "existing_prerequisites": prerequisites,
            "clarification_answers": {
                key: value.strip()
                for key, value in clarification_answers.items()
                if key in READINESS_QUESTIONS
                and isinstance(value, str)
                and value.strip()
            },
        }

    @staticmethod
    def _restore_application_owned_decomposition_envelope(
        raw: str,
        *,
        parent_task_id: int,
        proposal_id: str,
    ) -> str:
        """Keep application-owned proposal identity out of the model's authority."""
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
        if not isinstance(value, dict):
            return raw
        value = {
            **value,
            "proposal_type": PROPOSAL_TYPE,
            "parent_task_id": parent_task_id,
            "proposal_id": proposal_id,
            "requires_confirmation": True,
        }
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def request_decomposition(
        self,
        task: Task,
        clarification_answers: dict[str, str],
    ) -> ProposalResult:
        readiness = self.readiness(task, clarification_answers)
        if not readiness.ready:
            raise Phase6ValidationError(
                "More task information is required before generating a proposal."
            )
        resolved_model = self.model.model_identity()
        context = self.minimized_task_context(task, clarification_answers)
        fingerprint = self._fingerprint(
            {
                "prompt_version": DECOMPOSITION_PROMPT_VERSION,
                "context": context,
                "model": self.model.fingerprint_configuration(resolved_model),
                "generation": {"temperature": 0, "max_tokens": 1800},
            }
        )
        existing = self.proposals.find_draft_by_fingerprint(
            int(task.id), fingerprint
        )
        if existing is not None:
            return ProposalResult(
                self._from_stored_payload(existing.payload_json),
                fingerprint,
                True,
            )

        proposal_id = f"decomp-{uuid.uuid4()}"
        contract = {
            "output_contract_version": DECOMPOSITION_PROMPT_VERSION,
            "parent_task_id": task.id,
            "proposal_id": proposal_id,
            "selected_task": context,
        }
        raw = self.model.propose_decomposition(
            contract,
            resolved_model=resolved_model,
        )
        raw = self._restore_application_owned_decomposition_envelope(
            raw,
            parent_task_id=int(task.id),
            proposal_id=proposal_id,
        )
        validated = self.validate_decomposition_response(
            raw,
            parent_task=task,
            expected_proposal_id=proposal_id,
        )
        stored = DecompositionProposal(
            proposal_id=proposal_id,
            parent_task_id=int(task.id),
            payload_json=json.dumps(
                validated.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            fingerprint=fingerprint,
            status="draft",
        )
        self.proposals.save(stored)
        return ProposalResult(validated, fingerprint)

    @staticmethod
    def _original_content(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": item["title"],
            "description": item["description"],
            "estimated_hours": float(item["estimated_hours"]),
            "priority": item["priority"],
            "status": "Open",
            "completion_criterion": item["completion_criterion"],
            "due_date": item["due_date"],
        }

    @classmethod
    def _review_from_stored(cls, stored: DecompositionProposal) -> ProposalReview:
        try:
            payload = json.loads(stored.payload_json)
            if (
                payload.get("proposal_type") != PROPOSAL_TYPE
                or payload.get("proposal_id") != stored.proposal_id
                or payload.get("parent_task_id") != stored.parent_task_id
                or payload.get("requires_confirmation") is not True
            ):
                raise Phase7ValidationError(
                    "The persisted proposal identity or approval boundary is inconsistent."
                )
            original_items = payload["subtasks"]
            raw_review = payload.get("review")
            if raw_review is None:
                items = tuple(
                    ReviewItem(
                        item_key=item["item_key"],
                        title=item["title"],
                        description=item["description"],
                        estimated_hours=float(item["estimated_hours"]),
                        priority=item["priority"],
                        status="Open",
                        completion_criterion=item["completion_criterion"],
                        due_date=date.fromisoformat(item["due_date"])
                        if item["due_date"]
                        else None,
                        prerequisite_item_keys=tuple(item["prerequisite_item_keys"]),
                        selected=True,
                        display_order=index,
                        origin="ai",
                        original_content=cls._original_content(item),
                    )
                    for index, item in enumerate(original_items, start=1)
                )
            else:
                if raw_review.get("version") != 1 or not isinstance(
                    raw_review.get("items"), list
                ):
                    raise Phase7ValidationError(
                        "The persisted review format is unsupported."
                    )
                for item in raw_review["items"]:
                    if not isinstance(item, dict) or set(item) != REVIEW_ITEM_FIELDS:
                        raise Phase7ValidationError(
                            "A persisted review item has invalid fields."
                        )
                    if type(item["selected"]) is not bool or type(
                        item["display_order"]
                    ) is not int:
                        raise Phase7ValidationError(
                            "A persisted review selection or display order is invalid."
                        )
                items = tuple(
                    ReviewItem(
                        item_key=item["item_key"],
                        title=item["title"],
                        description=item["description"],
                        estimated_hours=float(item["estimated_hours"]),
                        priority=item["priority"],
                        status=item["status"],
                        completion_criterion=item["completion_criterion"],
                        due_date=date.fromisoformat(item["due_date"])
                        if item["due_date"]
                        else None,
                        prerequisite_item_keys=tuple(item["prerequisite_item_keys"]),
                        selected=item["selected"],
                        display_order=item["display_order"],
                        origin=item["origin"],
                        original_content=item.get("original_content"),
                    )
                    for item in raw_review["items"]
                )
        except Phase7ValidationError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise Phase7ValidationError(
                "The persisted proposal review state is malformed."
            ) from exc
        return ProposalReview(
            proposal_id=stored.proposal_id,
            parent_task_id=stored.parent_task_id,
            summary=payload["summary"],
            status=stored.status,
            items=tuple(sorted(items, key=lambda item: item.display_order)),
            advisories=tuple(
                ProposalAdvisory(item["kind"], item["message"])
                for item in payload.get("advisories", ())
            ),
        )

    def get_review(self, proposal_id: str) -> ProposalReview:
        return self._review_from_stored(self.proposals.get(proposal_id))

    def _save_review(self, review: ProposalReview) -> ProposalReview:
        stored = self.proposals.get(review.proposal_id)
        if stored.status != "draft":
            raise Phase7ValidationError(
                f"A {stored.status} proposal cannot be edited as a draft."
            )
        payload = json.loads(stored.payload_json)
        payload["review"] = {
            "version": 1,
            "items": [
                item.to_dict()
                for item in sorted(review.items, key=lambda value: value.display_order)
            ],
        }
        self.proposals.update_payload(
            review.proposal_id,
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        return self.get_review(review.proposal_id)

    @staticmethod
    def _replace_review_item(
        review: ProposalReview,
        item_key: str,
        replacement: ReviewItem | None,
    ) -> ProposalReview:
        found = False
        items: list[ReviewItem] = []
        for item in review.items:
            if item.item_key == item_key:
                found = True
                if replacement is not None:
                    items.append(replacement)
            else:
                items.append(item)
        if not found:
            raise KeyError(f"Review item {item_key} not found")
        items = [replace(item, display_order=index) for index, item in enumerate(
            sorted(items, key=lambda value: value.display_order), start=1
        )]
        return replace(review, items=tuple(items))

    def update_review_item(
        self,
        proposal_id: str,
        item_key: str,
        changes: dict[str, Any],
    ) -> ProposalReview:
        allowed = {
            "title", "description", "estimated_hours", "priority", "status",
            "completion_criterion", "due_date",
        }
        unsupported = set(changes) - allowed
        if unsupported:
            raise Phase7ValidationError(
                "Unsupported review fields: " + ", ".join(sorted(unsupported))
            )
        review = self.get_review(proposal_id)
        item = next((value for value in review.items if value.item_key == item_key), None)
        if item is None:
            raise KeyError(f"Review item {item_key} not found")
        values = item.content_dict()
        values.update(changes)
        if isinstance(values.get("due_date"), str):
            try:
                values["due_date"] = date.fromisoformat(values["due_date"])
            except ValueError as exc:
                raise Phase7ValidationError("A reviewed due date is invalid.") from exc
        if values.get("due_date") is not None and type(values["due_date"]) is not date:
            raise Phase7ValidationError("A reviewed due date must be a calendar date.")
        try:
            TaskService._validate_values(
                values, task_type="standard", require_title=True
            )
        except TaskValidationError as exc:
            raise Phase7ValidationError(str(exc)) from exc
        if values["priority"] not in VALID_PRIORITIES or values["status"] not in VALID_STATUSES:
            raise Phase7ValidationError("A reviewed task field is invalid.")
        values["estimated_hours"] = float(values["estimated_hours"])
        updated = replace(
            item,
            title=str(values["title"]).strip(),
            description=values["description"],
            estimated_hours=values["estimated_hours"],
            priority=values["priority"],
            status=values["status"],
            completion_criterion=values["completion_criterion"],
            due_date=values["due_date"],
        )
        return self._save_review(
            self._replace_review_item(review, item_key, updated)
        )

    def add_review_item(
        self,
        proposal_id: str,
        *,
        title: str,
        description: str = "",
        estimated_hours: float = 0.25,
        priority: str | None = None,
        status: str = "Open",
        completion_criterion: str = "",
        due_date: date | None = None,
    ) -> ProposalReview:
        review = self.get_review(proposal_id)
        parent = self.tasks.repo.get(review.parent_task_id)
        values = {
            "title": title,
            "description": description,
            "estimated_hours": estimated_hours,
            "priority": priority or parent.priority,
            "status": status,
            "completion_criterion": completion_criterion,
            "due_date": due_date,
        }
        if due_date is not None and type(due_date) is not date:
            raise Phase7ValidationError("A reviewed due date must be a calendar date.")
        try:
            TaskService._validate_values(values, task_type="standard", require_title=True)
        except TaskValidationError as exc:
            raise Phase7ValidationError(str(exc)) from exc
        item = ReviewItem(
            item_key=f"manual-{uuid.uuid4().hex}",
            title=title.strip(),
            description=description,
            estimated_hours=float(estimated_hours),
            priority=values["priority"],
            status=status,
            completion_criterion=completion_criterion,
            due_date=due_date,
            prerequisite_item_keys=(),
            selected=True,
            display_order=len(review.items) + 1,
            origin="user",
            original_content=None,
        )
        return self._save_review(replace(review, items=(*review.items, item)))

    def remove_review_item(self, proposal_id: str, item_key: str) -> ProposalReview:
        review = self.get_review(proposal_id)
        return self._save_review(self._replace_review_item(review, item_key, None))

    def set_review_item_selected(
        self, proposal_id: str, item_key: str, selected: bool
    ) -> ProposalReview:
        if not isinstance(selected, bool):
            raise Phase7ValidationError("Selection must be true or false.")
        review = self.get_review(proposal_id)
        item = next((value for value in review.items if value.item_key == item_key), None)
        if item is None:
            raise KeyError(f"Review item {item_key} not found")
        return self._save_review(
            self._replace_review_item(review, item_key, replace(item, selected=selected))
        )

    def set_review_prerequisites(
        self, proposal_id: str, item_key: str, prerequisite_item_keys: list[str]
    ) -> ProposalReview:
        if not isinstance(prerequisite_item_keys, list) or not all(
            isinstance(key, str) for key in prerequisite_item_keys
        ):
            raise Phase7ValidationError("Prerequisites must be proposal-local item keys.")
        review = self.get_review(proposal_id)
        item = next((value for value in review.items if value.item_key == item_key), None)
        if item is None:
            raise KeyError(f"Review item {item_key} not found")
        return self._save_review(
            self._replace_review_item(
                review,
                item_key,
                replace(item, prerequisite_item_keys=tuple(prerequisite_item_keys)),
            )
        )

    def reorder_review_items(
        self, proposal_id: str, ordered_item_keys: list[str]
    ) -> ProposalReview:
        review = self.get_review(proposal_id)
        current = {item.item_key: item for item in review.items}
        if len(ordered_item_keys) != len(set(ordered_item_keys)) or set(
            ordered_item_keys
        ) != set(current):
            raise Phase7ValidationError(
                "Reordering must include every review item exactly once."
            )
        items = tuple(
            replace(current[key], display_order=index)
            for index, key in enumerate(ordered_item_keys, start=1)
        )
        return self._save_review(replace(review, items=items))

    def move_review_item(
        self, proposal_id: str, item_key: str, direction: int
    ) -> ProposalReview:
        if direction not in {-1, 1}:
            raise Phase7ValidationError("Review items move one position at a time.")
        review = self.get_review(proposal_id)
        keys = [item.item_key for item in review.items]
        if item_key not in keys:
            raise KeyError(f"Review item {item_key} not found")
        index = keys.index(item_key)
        target = index + direction
        if target < 0 or target >= len(keys):
            return review
        keys[index], keys[target] = keys[target], keys[index]
        return self.reorder_review_items(proposal_id, keys)

    @classmethod
    def _validate_review_payload(
        cls,
        parent: Task,
        stored: DecompositionProposal,
    ) -> ReviewValidation:
        review = cls._review_from_stored(stored)
        if review.status != "draft":
            raise Phase7ValidationError(
                f"A {review.status} proposal cannot be approved as a draft."
            )
        if review.parent_task_id != parent.id:
            raise Phase7ValidationError("The current proposal parent is inconsistent.")
        if parent.task_type not in {"standard", "epic"}:
            raise Phase7ValidationError("The current parent hierarchy state is invalid.")
        keys = [item.item_key for item in review.items]
        if len(keys) != len(set(keys)):
            raise Phase7ValidationError("Review item keys must be unique.")
        if any(not re.fullmatch(r"[A-Za-z0-9_-]+", key) for key in keys):
            raise Phase7ValidationError("A review item key is invalid.")
        orders = [item.display_order for item in review.items]
        if set(orders) != set(range(1, len(review.items) + 1)):
            raise Phase7ValidationError(
                "Review display order must be unique and contiguous."
            )
        selected = review.selected_items
        if not 1 <= len(selected) <= 8:
            raise Phase7ValidationError(
                "Select between one and eight subtasks before approval."
            )

        payload = json.loads(stored.payload_json)
        originals = {
            item["item_key"]: cls._original_content(item)
            for item in payload["subtasks"]
        }
        for item in review.items:
            if item.item_key in originals:
                if item.origin != "ai" or item.original_content != originals[item.item_key]:
                    raise Phase7ValidationError(
                        "AI item origin or original content failed provenance verification."
                    )
            elif (
                item.origin != "user"
                or item.original_content is not None
                or not item.item_key.startswith("manual-")
            ):
                raise Phase7ValidationError(
                    "A manually added item failed provenance verification."
                )
            if not item.selected:
                continue
            try:
                TaskService._validate_values(
                    item.content_dict(), task_type="standard", require_title=True
                )
            except TaskValidationError as exc:
                raise Phase7ValidationError(
                    f"{item.title or item.item_key}: {exc}"
                ) from exc

        selected_keys = {item.item_key for item in selected}
        selected_by_key = {item.item_key: item for item in selected}
        for item in selected:
            prerequisites = item.prerequisite_item_keys
            if len(prerequisites) != len(set(prerequisites)):
                raise Phase7ValidationError(
                    f"{item.title} has duplicate prerequisite references."
                )
            if item.item_key in prerequisites:
                raise Phase7ValidationError(
                    f"{item.title} cannot depend on itself."
                )
            missing = set(prerequisites) - selected_keys
            if missing:
                raise Phase7ValidationError(
                    f"{item.title} references removed or deselected prerequisite(s): "
                    + ", ".join(sorted(missing))
                    + ". Select them again or remove the relationship."
                )
            if item.status == "Completed":
                incomplete = [
                    key
                    for key in prerequisites
                    if selected_by_key[key].status != "Completed"
                ]
                if incomplete:
                    raise Phase7ValidationError(
                        f"{item.title} cannot be completed while a selected "
                        "prerequisite remains incomplete: "
                        + ", ".join(incomplete)
                        + "."
                    )
        try:
            cls._validate_prerequisite_graph(
                [
                    ProposedSubtask(
                        item_key=item.item_key,
                        title=item.title,
                        description=item.description,
                        estimated_hours=item.estimated_hours,
                        priority=item.priority,
                        suggested_sequence=index,
                        completion_criterion=item.completion_criterion,
                        due_date=item.due_date,
                        prerequisite_item_keys=item.prerequisite_item_keys,
                    )
                    for index, item in enumerate(selected, start=1)
                ]
            )
        except Phase6ValidationError as exc:
            raise Phase7ValidationError(str(exc)) from exc
        warnings = cls._proposal_warnings(
            parent,
            [
                ProposedSubtask(
                    item_key=item.item_key,
                    title=item.title,
                    description=item.description,
                    estimated_hours=item.estimated_hours,
                    priority=item.priority,
                    suggested_sequence=index,
                    completion_criterion=item.completion_criterion,
                    due_date=item.due_date,
                    prerequisite_item_keys=item.prerequisite_item_keys,
                    provenance=item.provenance,
                )
                for index, item in enumerate(selected, start=1)
            ],
        )
        return ReviewValidation(review, warnings)

    def validate_review(self, proposal_id: str) -> ReviewValidation:
        stored = self.proposals.get(proposal_id)
        try:
            parent = self.tasks.repo.get(stored.parent_task_id)
        except KeyError as exc:
            raise Phase7ValidationError(
                "The proposal parent task no longer exists."
            ) from exc
        return self._validate_review_payload(parent, stored)

    def approve_review(
        self,
        proposal_id: str,
        *,
        failure_hook=None,
    ) -> ApprovalResult:
        def validate_current(parent: Task, payload_json: str) -> ReviewValidation:
            stored = DecompositionProposal(
                proposal_id=proposal_id,
                parent_task_id=int(parent.id),
                payload_json=payload_json,
                fingerprint="",
                status="draft",
            )
            return self._validate_review_payload(parent, stored)

        return self.proposals.approve_atomically(
            proposal_id, validate_current, failure_hook=failure_hook
        )

    def reject_review(self, proposal_id: str) -> ProposalReview:
        self.proposals.close_draft(proposal_id, "rejected")
        return self.get_review(proposal_id)

    def cancel_review(self, proposal_id: str) -> ProposalReview:
        self.proposals.close_draft(proposal_id, "cancelled")
        return self.get_review(proposal_id)

    @classmethod
    def validate_decomposition_response(
        cls,
        raw: str,
        *,
        parent_task: Task,
        expected_proposal_id: str,
    ) -> ValidatedDecompositionProposal:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise Phase6ValidationError("The model response was not valid JSON.") from exc
        if isinstance(value, dict) and "advisories" not in value:
            value = {**value, "advisories": []}
        cls._require_exact_fields(value, TOP_LEVEL_FIELDS, "proposal")
        if value["proposal_type"] != PROPOSAL_TYPE:
            raise Phase6ValidationError("The proposal type is invalid.")
        if isinstance(value["parent_task_id"], bool) or value["parent_task_id"] != parent_task.id:
            raise Phase6ValidationError("The proposal parent task does not match.")
        if value["proposal_id"] != expected_proposal_id:
            raise Phase6ValidationError("The application-owned proposal ID was altered.")
        if value["requires_confirmation"] is not True:
            raise Phase6ValidationError("The proposal must require confirmation.")
        summary = cls._bounded_text(
            value["summary"], "Summary", MAX_SUMMARY_LENGTH, required=True
        )
        cls._reject_unsafe_actionable_text((summary,))

        raw_subtasks = value["subtasks"]
        if not isinstance(raw_subtasks, list) or not 2 <= len(raw_subtasks) <= 8:
            raise Phase6ValidationError("A proposal must contain between 2 and 8 subtasks.")
        sequence_values = [
            item.get("suggested_sequence") if isinstance(item, dict) else None
            for item in raw_subtasks
        ]
        if (
            all(
                isinstance(sequence, int) and not isinstance(sequence, bool)
                for sequence in sequence_values
            )
            and set(sequence_values) == set(range(len(raw_subtasks)))
        ):
            raw_subtasks = [
                {**item, "suggested_sequence": item["suggested_sequence"] + 1}
                for item in raw_subtasks
            ]

        subtasks: list[ProposedSubtask] = []
        seen_keys: set[str] = set()
        seen_titles: set[str] = set()
        seen_sequences: set[int] = set()
        removed_unanchored_due_dates = False
        removed_self_dependencies: list[str] = []
        for raw_item in raw_subtasks:
            cls._require_exact_fields(raw_item, SUBTASK_FIELDS, "subtask")
            item_key = cls._bounded_text(raw_item["item_key"], "Item key", 40, True)
            if not re.fullmatch(r"[A-Za-z0-9_-]+", item_key):
                raise Phase6ValidationError("Item keys may use letters, numbers, _ and - only.")
            if item_key in seen_keys:
                raise Phase6ValidationError("Proposal item keys must be unique.")
            seen_keys.add(item_key)
            title = cls._bounded_text(raw_item["title"], "Title", TITLE_MAX_LENGTH, True)
            normalized_title = " ".join(title.casefold().split())
            if normalized_title in seen_titles:
                raise Phase6ValidationError("Proposed subtask titles must be unique.")
            seen_titles.add(normalized_title)
            description = cls._bounded_text(
                raw_item["description"],
                "Description",
                DESCRIPTION_MAX_LENGTH,
                True,
            )
            completion = cls._bounded_text(
                raw_item["completion_criterion"],
                "Completion criterion",
                DESCRIPTION_MAX_LENGTH,
                True,
            )
            estimate = cls._validate_estimate(raw_item["estimated_hours"])
            priority = raw_item["priority"]
            if not isinstance(priority, str) or priority not in VALID_PRIORITIES:
                raise Phase6ValidationError("A proposed priority is invalid.")
            if priority != parent_task.priority:
                raise Phase6ValidationError(
                    "Proposed priority must use the deterministic inherited parent priority."
                )
            sequence = raw_item["suggested_sequence"]
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                raise Phase6ValidationError("Suggested sequence values must be positive integers.")
            if sequence in seen_sequences:
                raise Phase6ValidationError("Suggested sequence values must be unique.")
            seen_sequences.add(sequence)
            raw_due_date = raw_item["due_date"]
            if parent_task.due_date is None and raw_due_date is not None:
                raw_due_date = None
                removed_unanchored_due_dates = True
            due_date = cls._validate_date(raw_due_date)
            raw_prerequisites = raw_item["prerequisite_item_keys"]
            if not isinstance(raw_prerequisites, list) or not all(
                isinstance(key, str) for key in raw_prerequisites
            ):
                raise Phase6ValidationError("Prerequisite references must be a list of item keys.")
            if len(raw_prerequisites) != len(set(raw_prerequisites)):
                raise Phase6ValidationError("Prerequisite references must be unique.")
            if item_key in raw_prerequisites:
                raw_prerequisites = [
                    key for key in raw_prerequisites if key != item_key
                ]
                removed_self_dependencies.append(title)
            cls._reject_unsafe_actionable_text(
                (title, description, completion),
            )
            subtasks.append(
                ProposedSubtask(
                    item_key=item_key,
                    title=title,
                    description=description,
                    estimated_hours=estimate,
                    priority=priority,
                    suggested_sequence=sequence,
                    completion_criterion=completion,
                    due_date=due_date,
                    prerequisite_item_keys=tuple(raw_prerequisites),
                )
            )

        if seen_sequences != set(range(1, len(subtasks) + 1)):
            raise Phase6ValidationError("Suggested sequence must be contiguous from 1.")
        cls._validate_prerequisite_graph(subtasks)

        raw_advisories = value["advisories"]
        if not isinstance(raw_advisories, list) or len(raw_advisories) > MAX_ADVISORIES:
            raise Phase6ValidationError("The advisory list exceeds its bounded limit.")
        advisories: list[ProposalAdvisory] = []
        for raw_advisory in raw_advisories:
            cls._require_exact_fields(raw_advisory, ADVISORY_FIELDS, "advisory")
            kind = raw_advisory["kind"]
            if not isinstance(kind, str) or kind not in VALID_ADVISORY_KINDS:
                raise Phase6ValidationError("An advisory kind is unsupported.")
            message = cls._bounded_text(
                raw_advisory["message"],
                "Advisory",
                MAX_ADVISORY_LENGTH,
                True,
            )
            cls._reject_unsafe_actionable_text((message,))
            advisories.append(ProposalAdvisory(kind, message))

        warnings = cls._proposal_warnings(parent_task, subtasks)
        if removed_unanchored_due_dates:
            warnings = (
                "Generated subtask due dates were removed because the parent "
                "task has no due date.",
                *warnings,
            )
        if removed_self_dependencies:
            labels = ", ".join(removed_self_dependencies)
            warnings = (
                f"Removed an impossible self-dependency from: {labels}. "
                "Review prerequisite links before approval.",
                *warnings,
            )
        return ValidatedDecompositionProposal(
            proposal_type=PROPOSAL_TYPE,
            parent_task_id=int(parent_task.id),
            proposal_id=expected_proposal_id,
            summary=summary,
            requires_confirmation=True,
            subtasks=tuple(sorted(subtasks, key=lambda item: item.suggested_sequence)),
            advisories=tuple(advisories),
            warnings=warnings,
        )

    @staticmethod
    def _require_exact_fields(value: Any, expected: set[str], label: str) -> None:
        if not isinstance(value, dict):
            raise Phase6ValidationError(f"Each {label} must be a JSON object.")
        actual = set(value)
        if actual != expected:
            missing = sorted(expected - actual)
            unsupported = sorted(actual - expected)
            detail = []
            if missing:
                detail.append(f"missing: {', '.join(missing)}")
            if unsupported:
                detail.append(f"unsupported: {', '.join(unsupported)}")
            raise Phase6ValidationError(
                f"The {label} fields are invalid ({'; '.join(detail)})."
            )

    @staticmethod
    def _bounded_text(
        value: Any,
        label: str,
        maximum: int,
        required: bool = False,
    ) -> str:
        if not isinstance(value, str):
            raise Phase6ValidationError(f"{label} must be text.")
        stripped = value.strip()
        if required and not stripped:
            raise Phase6ValidationError(f"{label} is required.")
        if len(value) > maximum:
            raise Phase6ValidationError(f"{label} exceeds {maximum:,} characters.")
        return stripped if required else value

    @staticmethod
    def _validate_estimate(value: Any) -> float:
        if isinstance(value, bool):
            raise Phase6ValidationError("Estimated hours must be numeric.")
        try:
            estimate = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise Phase6ValidationError("Estimated hours must be numeric.") from None
        if (
            not estimate.is_finite()
            or estimate <= 0
            or estimate > STANDARD_ESTIMATE_MAX_HOURS
            or estimate * 4 != (estimate * 4).to_integral_value()
        ):
            raise Phase6ValidationError(
                "Estimates must be positive quarter-hour values within the task limit."
            )
        return float(estimate)

    @staticmethod
    def _validate_date(value: Any) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise Phase6ValidationError("Due dates must use ISO YYYY-MM-DD format or null.")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise Phase6ValidationError("A proposed due date is invalid.") from exc
        if parsed.isoformat() != value:
            raise Phase6ValidationError("Due dates must use ISO YYYY-MM-DD format.")
        return parsed

    @staticmethod
    def _reject_unsafe_actionable_text(values: tuple[str, ...]) -> None:
        combined = "\n".join(values)
        for pattern in UNSAFE_ACTIONABLE_PATTERNS:
            if re.search(pattern, combined, flags=re.IGNORECASE | re.DOTALL):
                raise Phase6ValidationError(
                    "Actionable proposal fields contained unsafe instructions or commands."
                )

    @staticmethod
    def _validate_prerequisite_graph(subtasks: list[ProposedSubtask]) -> None:
        keys = {item.item_key for item in subtasks}
        adjacency = {
            item.item_key: set(item.prerequisite_item_keys) for item in subtasks
        }
        for prerequisites in adjacency.values():
            if not prerequisites.issubset(keys):
                raise Phase6ValidationError(
                    "A prerequisite references an item outside this proposal."
                )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visiting:
                raise Phase6ValidationError("Proposed prerequisites contain a cycle.")
            if key in visited:
                return
            visiting.add(key)
            for prerequisite in adjacency[key]:
                visit(prerequisite)
            visiting.remove(key)
            visited.add(key)

        for key in keys:
            visit(key)

    @staticmethod
    def _proposal_warnings(
        parent: Task,
        subtasks: list[ProposedSubtask],
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        late = [
            item
            for item in subtasks
            if parent.due_date is not None
            and item.due_date is not None
            and item.due_date > parent.due_date
        ]
        if late:
            labels = ", ".join(item.title for item in late)
            warnings.append(
                f"Proposed due date is later than the parent due date for: {labels}."
            )
        total = sum(item.estimated_hours for item in subtasks)
        if parent.estimated_hours is not None:
            difference = abs(total - parent.estimated_hours)
            threshold = max(2.0, parent.estimated_hours * 0.25)
            if difference >= threshold:
                warnings.append(
                    f"Original estimate: {parent.estimated_hours:g} hours. "
                    f"Proposed subtask total: {total:g} hours."
                )
        return tuple(warnings)

    @staticmethod
    def _from_stored_payload(payload_json: str) -> ValidatedDecompositionProposal:
        value = json.loads(payload_json)
        subtasks = tuple(
            ProposedSubtask(
                item_key=item["item_key"],
                title=item["title"],
                description=item["description"],
                estimated_hours=float(item["estimated_hours"]),
                priority=item["priority"],
                suggested_sequence=int(item["suggested_sequence"]),
                completion_criterion=item["completion_criterion"],
                due_date=date.fromisoformat(item["due_date"])
                if item["due_date"]
                else None,
                prerequisite_item_keys=tuple(item["prerequisite_item_keys"]),
                provenance="ai_generated",
            )
            for item in value["subtasks"]
        )
        advisories = tuple(
            ProposalAdvisory(item["kind"], item["message"])
            for item in value["advisories"]
        )
        return ValidatedDecompositionProposal(
            proposal_type=value["proposal_type"],
            parent_task_id=int(value["parent_task_id"]),
            proposal_id=value["proposal_id"],
            summary=value["summary"],
            requires_confirmation=True,
            subtasks=subtasks,
            advisories=advisories,
            warnings=tuple(value.get("warnings", ())),
        )
