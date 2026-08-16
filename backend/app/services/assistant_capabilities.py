"""Bounded semantic intent classification and read-only capability dispatch."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SUPPORTED_INTENTS = (
    "workflow_status", "blocker_or_failure", "completed_work", "remaining_work",
    "analysis_explanation", "planning_explanation", "transformation_explanation",
    "validation_explanation", "evidence_question", "usage_and_cost", "next_steps",
    "comparison", "general_migration_question", "unsupported",
)
IntentName = Literal[
    "workflow_status", "blocker_or_failure", "completed_work", "remaining_work",
    "analysis_explanation", "planning_explanation", "transformation_explanation",
    "validation_explanation", "evidence_question", "usage_and_cost", "next_steps",
    "comparison", "general_migration_question", "unsupported",
]


class SemanticIntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    intent: IntentName
    rationale: str = Field(min_length=1)


MUTATION_PATTERNS = (
    r"\b(approve|reject|execute|apply|patch|modify)\b",
    r"\bchange\b.*\b(workflow|state|files?)\b",
    r"\bretry\b.*\b(command|migration|repair)\b",
    r"\bstart\b.*\b(repair|migration|command)\b",
    r"\brun\s+(a\s+)?command\b",
)

_STOP_WORDS = frozenset(["a", "an", "and", "are", "during", "for", "has", "how", "is", "latest", "of", "the", "should", "this", "to", "what", "why", "with", "you"])
_INTENT_PROFILES: dict[str, tuple[str, ...]] = {
    "usage_and_cost": ("usage cost tokens model consumption spent duration time recorded budget",),
    "blocker_or_failure": ("blocked blocker failure failed stopped stop error incident issue",),
    "evidence_question": ("evidence supports proof source artifact citation",),
    "comparison": ("compare comparison differ difference versus previous changed",),
    "next_steps": ("next after follow proceed happen proposal",),
    "completed_work": ("completed finished done achieved",),
    "remaining_work": ("remaining still needs left outstanding",),
    "analysis_explanation": ("analysis findings discovery result",),
    "planning_explanation": ("planning plan planned rationale",),
    "transformation_explanation": ("transformation changed change edits migration",),
    "validation_explanation": ("validation tests lint verification failure result",),
    "workflow_status": ("current where migration state status workflow phase gate progress",),
}


def _semantic_tokens(text: str) -> frozenset[str]:
    return frozenset(token for token in re.findall(r"[a-z0-9]+", text.casefold()) if token not in _STOP_WORDS)


def is_mutation_request(question: str) -> bool:
    normalized = " ".join(question.lower().split())
    return any(re.search(pattern, normalized) for pattern in MUTATION_PATTERNS)


@dataclass(frozen=True)
class AssistantCapability:
    capability_key: str
    supported_intents: frozenset[str]
    required_projection_fields: frozenset[str] = frozenset()
    allowed_evidence_types: frozenset[str] = frozenset()
    context_builder: Callable[..., object] | None = None
    response_policy: str = "read_only"
    next_step_proposal_builder: Callable[..., list[dict[str, object]]] | None = None

    def provider_policy(self, *, selected_intent: str, selected_excerpt_ids: list[str]) -> str:
        """Return the machine-readable response contract for this dispatch."""
        return json.dumps({
            "selected_intent": selected_intent,
            "selected_capability_key": self.capability_key,
            "required_authoritative_projection_fields": sorted(self.required_projection_fields),
            "allowed_evidence_types": sorted(self.allowed_evidence_types),
            "citations_required": selected_intent == "evidence_question" and bool(selected_excerpt_ids),
            "allowed_proof_labels": (["approved_evidence_supported"] if selected_excerpt_ids else ["unknown_or_unavailable"])
            if selected_intent == "evidence_question" else [
                "authoritative_persisted_fact", "model_interpretation", "unknown_or_unavailable",
            ],
            "allowed_next_step_proposals": "read_only_navigation_only",
            "next_step_proposals": "Return an empty list unless the current authoritative projection contains an already-typed navigation-only proposal; never author a new command, retry, approval, repair, or workflow action.",
            "unknown_information_behavior": "state_unknown_or_unavailable",
            "answer_order": ["direct_answer", "short_explanation", "current_status_or_next_action_when_relevant", "evidence_used_when_useful"],
            "authority_order": ["current_authoritative_projection", "current_validated_evidence", "historical_evidence", "conversation_history"],
            "language": "Use human-facing workflow language; keep internal IDs, gate codes, stage suffixes, phase/status key-value dumps, and state numbers for details or when explicitly requested.",
            "primary_answer_rules": [
                "Answer simple questions simply; do not dump the projection or completed-work list unless asked.",
                "Current authoritative status outranks historical events and conversation history.",
                "If a failure is historical or resolved, label it historical and never present it as the current blocker.",
                "Describe stages as readable routes such as Angular 20 → 21 when the route is available.",
            ],
        }, sort_keys=True)


class AssistantCapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[str, AssistantCapability] = {}

    def register(self, capability: AssistantCapability) -> None:
        if capability.response_policy not in {"read_only", "strict_read_only"}:
            raise ValueError("Assistant capabilities must be read-only")
        collisions = [item.capability_key for item in self._items.values() if item.supported_intents & capability.supported_intents]
        if collisions:
            existing_intents = set().union(*(self._items[key].supported_intents for key in collisions))
            raise ValueError(f"Intent already registered: {sorted(capability.supported_intents & existing_intents)}")
        self._items[capability.capability_key] = capability

    def get_for_intent(self, intent: str) -> AssistantCapability | None:
        return next((item for item in self._items.values() if intent in item.supported_intents), None)

    def get(self, key: str) -> AssistantCapability | None:
        return self._items.get(key)

    def dispatch(self, result: SemanticIntentResult | str) -> AssistantCapability | None:
        intent = result.intent if isinstance(result, SemanticIntentResult) else result
        return self.get_for_intent(intent)

    def all(self) -> tuple[AssistantCapability, ...]:
        return tuple(self._items.values())


def build_next_step_proposals(*, run_id: str, gate_id: str | None, gate_state: str | None, blocker_phase: str | None, terminal: bool, waiting_reason: str | None, command_failed: bool = False) -> list[dict[str, object]]:
    """Build typed, navigation-only proposals from already projected state."""
    proposals: list[dict[str, object]] = []
    if gate_id and str(gate_state).lower() in {"pending", "waiting", "in_review"}:
        route = {"G02": f"/api/v1/runs/{run_id}/approvals/G02", "G04": f"/api/v1/runs/{run_id}/analysis", "G05": f"/api/v1/runs/{run_id}/feasibility", "G06": f"/api/v1/runs/{run_id}/plan/review"}.get(gate_id)
        if route:
            proposals.append({"action_key": f"review_{gate_id.lower()}", "label": f"Review {gate_id} approval", "reason": waiting_reason or f"{gate_id} is pending human review.", "target_route": route, "requires_human_approval": True, "executable_by_assistant": False})
    if blocker_phase == "runtime_resolution":
        proposals.append({"action_key": "retry_runtime_profile_resolution", "label": "Retry runtime-profile resolution", "reason": "Install or expose an approved paired Node/npm/npx runtime, then retry the governed resolution.", "target_route": f"/api/v1/runs/{run_id}/execution-profiles", "requires_human_approval": False, "executable_by_assistant": False})
    if command_failed and not terminal:
        proposals.append({"action_key": "review_command_failure", "label": "Review failed command", "reason": "The latest command failed and its governed recovery state must be reviewed.", "target_route": f"/api/v1/runs/{run_id}/commands", "requires_human_approval": True, "executable_by_assistant": False})
    return proposals


def default_capability_registry() -> AssistantCapabilityRegistry:
    registry = AssistantCapabilityRegistry()
    for key, intents, fields, evidence in (
        ("workflow_status", {"workflow_status", "completed_work", "remaining_work", "comparison"}, {"status", "phase", "stage", "gate", "blocker", "historical_failures", "next_action", "repair_state", "repair_context", "latest_command_result", "events"}, set()),
        ("failure_explanation", {"blocker_or_failure"}, {"status", "phase", "stage", "blocker", "historical_failures", "failure_reason", "next_action", "repair_state", "repair_context", "latest_command_result", "events"}, set()),
        ("analysis", {"analysis_explanation", "evidence_question"}, {"events", "evidence", "status", "phase", "stage", "blocker", "next_action"}, {"report", "analysis", "snapshot", "source"}),
        ("planning", {"planning_explanation"}, {"events", "phase", "stage", "gate"}, {"plan", "report"}),
        ("transformation", {"transformation_explanation"}, {"events", "phase", "stage", "repair_state", "repair_context", "latest_command_result"}, {"report", "snapshot"}),
        ("validation", {"validation_explanation"}, {"events", "phase", "stage", "failure_reason", "latest_command_result"}, {"report", "validation"}),
        ("usage", {"usage_and_cost"}, {"usage", "duration_seconds"}, set()),
        ("next_steps", {"next_steps"}, {"blocker", "gate", "next_action", "waiting_reason"}, set()),
        ("general_migration_question", {"general_migration_question"}, set(), set()),
    ):
        registry.register(AssistantCapability(key, frozenset(intents), frozenset(fields), frozenset(evidence), response_policy="strict_read_only"))
    return registry


def classify_semantic_intent(question: str) -> SemanticIntentResult:
    """Return a typed, bounded semantic classification and fail closed."""
    if not isinstance(question, str) or not question.strip() or is_mutation_request(question):
        return SemanticIntentResult(intent="unsupported", rationale="mutation_or_invalid_request")
    normalized = " ".join(question.casefold().split())
    if re.search(r"\bwhy\b.*\b(reviewer|review|request changes|repair)\b", normalized):
        return SemanticIntentResult(intent="blocker_or_failure", rationale="repair_review_question")
    if re.search(r"\b(what|which|show|explain)\b.*\b(repair|proposal|diff|changed)\b", normalized):
        return SemanticIntentResult(intent="transformation_explanation", rationale="repair_change_question")
    if re.search(r"\b(previous|prior|last)\b.*\brepair\b.*\b(work|succeed|pass|fail)", normalized):
        return SemanticIntentResult(intent="blocker_or_failure", rationale="repair_history_question")
    if "failure" in normalized and ("still current" in normalized or "current" in normalized):
        return SemanticIntentResult(intent="blocker_or_failure", rationale="current_vs_historical_failure_question")
    if re.search(r"\b(what|where|how)\b.*\b(happened|happening|progress|status|waiting|next)\b", normalized) or re.search(r"\b(where are we|what happened so far|current status)\b", normalized):
        return SemanticIntentResult(intent="workflow_status", rationale="current_workflow_question")
    if re.search(r"\b(what|who)\b.*\b(needs?|awaiting|waiting)\b.*\bapproval|\bapproval\b", normalized):
        return SemanticIntentResult(intent="workflow_status", rationale="approval_status_question")
    if re.search(r"\b(why|what|explain)\b.*\b(stopped?|blocked?|preventing|blocker|fail(ed|ure)?|error)\b", normalized) or "what is preventing progress" in normalized:
        return SemanticIntentResult(intent="blocker_or_failure", rationale="blocker_question")
    composite = (
        (re.search(r"\bwhy\b.*\b(stop|stopped|blocked|blocker|prevent|failure|failed)\b", normalized) and re.search(r"\b(next|happen|action|step)\b", normalized))
        or ("blocker" in normalized and re.search(r"\b(next|action|step)\b", normalized))
        or normalized in {"what is the next permitted action?", "what is the next permitted action"}
    )
    if composite:
        return SemanticIntentResult(intent="blocker_or_failure", rationale="composite_blocker_and_next_action")
    query_tokens = _semantic_tokens(question)
    scores = {intent: len(query_tokens & _semantic_tokens(profile[0])) for intent, profile in _INTENT_PROFILES.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0 or list(scores.values()).count(scores[best]) > 1:
        return SemanticIntentResult(intent="unsupported", rationale="no_unambiguous_supported_intent")
    return SemanticIntentResult(intent=best, rationale=f"semantic_profile_overlap={scores[best]}")


def _mutation_detected(question: str) -> bool:
    """Detect mutation intent using word-level matching to avoid substring gaps."""
    q = question.lower()
    words = set(q.split())
    punctuation = ",.;:!?"
    clean = q.translate(str.maketrans("", "", punctuation))
    clean_words = set(clean.split())
    mutation_keywords = {"approve", "reject", "execute", "apply", "patch"}
    if mutation_keywords & clean_words:
        return True
    if "change" in clean_words and ("workflow" in clean_words or "state" in clean_words):
        return True
    if "run" in clean_words and "command" in clean_words:
        return True
    if "modify" in clean_words and "files" in clean_words:
        return True
    return False


def classify_intent(question: str) -> str:
    """Compatibility adapter preserving the DEV general-question fallback."""
    result = classify_semantic_intent(question)
    if result.intent == "unsupported" and isinstance(question, str) and question.strip() and not is_mutation_request(question):
        return "general_migration_question"
    return result.intent
