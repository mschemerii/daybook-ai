from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
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
    ProposalAdvisory,
    ProposedSubtask,
    RankingFacts,
    ReadinessAssessment,
    Task,
    ValidatedDecompositionProposal,
)
from src.repositories.planning_repository import PlanningRepository
from src.services.task_service import (
    DESCRIPTION_MAX_LENGTH,
    STANDARD_ESTIMATE_MAX_HOURS,
    TITLE_MAX_LENGTH,
    VALID_PRIORITIES,
    TaskService,
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
    """Owns Phase 6 AI boundaries; it never creates or updates tasks."""

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

        subtasks: list[ProposedSubtask] = []
        seen_keys: set[str] = set()
        seen_titles: set[str] = set()
        seen_sequences: set[int] = set()
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
            due_date = cls._validate_date(raw_item["due_date"])
            raw_prerequisites = raw_item["prerequisite_item_keys"]
            if not isinstance(raw_prerequisites, list) or not all(
                isinstance(key, str) for key in raw_prerequisites
            ):
                raise Phase6ValidationError("Prerequisite references must be a list of item keys.")
            if len(raw_prerequisites) != len(set(raw_prerequisites)):
                raise Phase6ValidationError("Prerequisite references must be unique.")
            if item_key in raw_prerequisites:
                raise Phase6ValidationError("A proposed subtask cannot depend on itself.")
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
