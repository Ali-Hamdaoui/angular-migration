"""Deterministic in-process registry for governed Assistant capabilities."""

from dataclasses import dataclass
from typing import Callable


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
        self._items[capability.capability_key] = capability

    def get_for_intent(self, intent: str) -> AssistantCapability | None:
        return next((item for item in self._items.values() if intent in item.supported_intents), None)

    def get(self, key: str) -> AssistantCapability | None:
        return self._items.get(key)

    def all(self) -> tuple[AssistantCapability, ...]:
        return tuple(self._items.values())


def default_capability_registry() -> AssistantCapabilityRegistry:
    registry = AssistantCapabilityRegistry()
    for key, intent in (
        ("workflow_status", "workflow_status"),
        ("failure_explanation", "blocker_or_failure"),
        ("completed_work", "completed_work"),
        ("analysis", "analysis_explanation"),
        ("planning", "planning_explanation"),
        ("transformation", "transformation_explanation"),
        ("validation", "validation_explanation"),
        ("usage", "usage_and_cost"),
        ("next_steps", "next_steps"),
        ("general_migration_question", "general_migration_question"),
    ):
        registry.register(AssistantCapability(key, frozenset({intent}), response_policy="strict_read_only"))
    return registry


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
    """Classify common migration questions; unknown read-only questions stay answerable."""
    q = " ".join(question.lower().split())
    if _mutation_detected(q):
        return "unsupported"  # the caller converts this to the explicit mutation guard
    if any(term in q for term in ("token", "cost", "usage", "consumed", "duration")):
        return "usage_and_cost"
    if any(term in q for term in ("current migration", "migration state", "where is", "what is the current", "workflow", "status", "gate")):
        return "workflow_status"
    if any(term in q for term in ("why", "stop", "blocker", "failure", "failed", "error", "root cause")):
        return "blocker_or_failure"
    if any(term in q for term in ("completed", "done", "finished")):
        return "completed_work"
    if "after" in q or "next" in q or "should happen" in q:
        return "next_steps"
    if any(term in q for term in ("analysis", "discover")):
        return "analysis_explanation"
    if any(term in q for term in ("planning", "plan")):
        return "planning_explanation"
    if any(term in q for term in ("transform", "changed")):
        return "transformation_explanation"
    if any(term in q for term in ("validation", "test", "lint")):
        return "validation_explanation"
    return "general_migration_question"
