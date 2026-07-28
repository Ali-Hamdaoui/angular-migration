"""Bounded semantic intent classification and read-only capability dispatch."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SUPPORTED_INTENTS = (
    "workflow_status", "blocker_or_failure", "completed_work", "remaining_work",
    "analysis_explanation", "planning_explanation", "transformation_explanation",
    "validation_explanation", "evidence_question", "usage_and_cost", "next_steps",
    "comparison", "unsupported",
)
IntentName = Literal[
    "workflow_status", "blocker_or_failure", "completed_work", "remaining_work",
    "analysis_explanation", "planning_explanation", "transformation_explanation",
    "validation_explanation", "evidence_question", "usage_and_cost", "next_steps",
    "comparison", "unsupported",
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
    "usage_and_cost": ("usage cost tokens model consumption spent duration time recorded budget" ,),
    "blocker_or_failure": ("blocked blocker failure failed stopped stop error incident issue" ,),
    "evidence_question": ("evidence supports proof source artifact citation" ,),
    "comparison": ("compare comparison differ difference versus previous changed" ,),
    "next_steps": ("next after follow proceed happen proposal" ,),
    "completed_work": ("completed finished done achieved" ,),
    "remaining_work": ("remaining still needs left outstanding" ,),
    "analysis_explanation": ("analysis findings discovery result" ,),
    "planning_explanation": ("planning plan planned rationale" ,),
    "transformation_explanation": ("transformation changed change edits migration" ,),
    "validation_explanation": ("validation tests lint verification failure result" ,),
    "workflow_status": ("current where migration state status workflow phase gate progress" ,),
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


class AssistantCapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[str, AssistantCapability] = {}

    def register(self, capability: AssistantCapability) -> None:
        if capability.response_policy != "read_only":
            raise ValueError("Assistant capabilities must be read-only")
        collisions = [item.capability_key for item in self._items.values() if item.supported_intents & capability.supported_intents]
        if collisions:
            raise ValueError(f"Intent already registered: {sorted(capability.supported_intents & set().union(*(self._items[key].supported_intents for key in collisions)))}")
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


def default_capability_registry() -> AssistantCapabilityRegistry:
    registry = AssistantCapabilityRegistry()
    for key, intents in (
        ("workflow_status", {"workflow_status", "completed_work", "remaining_work", "comparison"}),
        ("failure_explanation", {"blocker_or_failure"}),
        ("analysis", {"analysis_explanation", "evidence_question"}),
        ("planning", {"planning_explanation"}),
        ("transformation", {"transformation_explanation"}),
        ("validation", {"validation_explanation"}),
        ("usage", {"usage_and_cost"}),
        ("next_steps", {"next_steps"}),
    ):
        registry.register(AssistantCapability(key, frozenset(intents), response_policy="read_only"))
    return registry


def classify_semantic_intent(question: str) -> SemanticIntentResult:
    """Return a typed, bounded semantic classification and fail closed.

    The classifier uses intent descriptions and normalized concept features, not an
    ordered exact-phrase router. It is intentionally local and bounded; the
    governed response call remains the sole answer generator.
    """
    if not isinstance(question, str) or not question.strip() or is_mutation_request(question):
        return SemanticIntentResult(intent="unsupported", rationale="mutation_or_invalid_request")
    query_tokens = _semantic_tokens(question)
    scores = {
        intent: len(query_tokens & _semantic_tokens(profile[0]))
        for intent, profile in _INTENT_PROFILES.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0 or list(scores.values()).count(scores[best]) > 1:
        return SemanticIntentResult(intent="unsupported", rationale="no_unambiguous_supported_intent")
    return SemanticIntentResult(intent=best, rationale=f"semantic_profile_overlap={scores[best]}")


def classify_intent(question: str) -> str:
    """Compatibility adapter returning the typed classifier's intent value."""
    return classify_semantic_intent(question).intent
