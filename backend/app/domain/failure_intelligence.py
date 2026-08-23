"""Failure intelligence contracts (V2 F19).

A coherent intelligence layer over diagnostic packs: a typed classification
taxonomy, stable grouping keys, deterministic root-cause resolution, and a
failure dependency graph.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


FailureTaxonomy = Literal["environment", "command", "dependency", "workflow", "state", "transport", "llm", "policy", "unknown"]


class FailureGroup(_ImmutableModel):
    """A stable group of related failures keyed deterministically."""

    group_key: str = Field(min_length=1)
    taxonomy: FailureTaxonomy = "unknown"
    fault_codes: tuple[str, ...] = Field(default_factory=tuple)
    member_count: int = Field(ge=1)
    first_seen: datetime
    last_seen: datetime
    signature: str = Field(default="")
    checksum: str = ""

    def bind_checksum(self) -> FailureGroup:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


class FailureRootCause(_ImmutableModel):
    """The deterministic root cause of a failure group."""

    group_key: str = Field(min_length=1)
    root_cause_code: str = Field(min_length=1)
    taxonomy: FailureTaxonomy = "unknown"
    explanation: str = Field(default="")
    confidence: Literal["high", "medium", "low"] = "medium"
    contributing_codes: tuple[str, ...] = Field(default_factory=tuple)


class FailureDependencyEdge(_ImmutableModel):
    """A dependency between two failure groups (blocker -> dependent)."""

    depends_on: str = Field(min_length=1)  # the failure that blocks
    dependent: str = Field(min_length=1)   # the failure that follows
    reason: str = Field(default="")


class FailureDependencyGraph(_ImmutableModel):
    """The dependency graph among failure groups."""

    nodes: tuple[FailureGroup, ...] = Field(default_factory=tuple)
    edges: tuple[FailureDependencyEdge, ...] = Field(default_factory=tuple)
    checksum: str = ""

    def bind_checksum(self) -> FailureDependencyGraph:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def now_utc() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# V2.2 P1-0 / section 13 — evidence-first failure ownership.
# ---------------------------------------------------------------------------

#: Proven failure phases, ordered by deterministic routing precedence.
FailurePhase = Literal[
    "HARNESS", "RUNTIME", "DEPENDENCY", "LOCKFILE", "DETERMINISTIC_SOURCE", "MAIN_REPAIR"
]

#: Proven owners; platform/runtime/dependency/lock categories never reach the
#: source Repair LLM.
FailureOwner = Literal[
    "PLATFORM_RECOVERY",
    "RUNTIME_RESOLVER",
    "COMPATIBILITY_PLANNER",
    "LOCK_RESOLVER",
    "DETERMINISTIC_REPAIR",
    "MAIN_REPAIR_LLM",
    "HUMAN",
]


class FailureDecision(_ImmutableModel):
    """One persisted, phase-first ownership decision (§13)."""

    schema_version: str = "failure-decision-v1"
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    node: str = Field(min_length=1)
    phase: FailurePhase
    owner: FailureOwner
    category: str = Field(min_length=1)
    reason_codes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    confidence: Literal["high", "medium", "low"] = "high"
    retryable: bool = False
    completeness_state: str | None = None
    dependency_intent_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    npm_capability_policy_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    checksum: str = ""

    def bind_checksum(self) -> "FailureDecision":
        canonical = self.model_dump(mode="json", exclude_none=True)
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


#: Phase -> owner mapping; deterministic and mutually exclusive.
PHASE_OWNERS: dict[str, FailureOwner] = {
    "HARNESS": "PLATFORM_RECOVERY",
    "RUNTIME": "RUNTIME_RESOLVER",
    "DEPENDENCY": "COMPATIBILITY_PLANNER",
    "LOCKFILE": "LOCK_RESOLVER",
    "DETERMINISTIC_SOURCE": "DETERMINISTIC_REPAIR",
    "MAIN_REPAIR": "MAIN_REPAIR_LLM",
}

#: Evidence-code prefixes per phase.  Phase/evidence precede message regexes;
#: the classifier never inspects stderr text for ownership.
_PHASE_EVIDENCE_PREFIXES: tuple[tuple[str, str], ...] = (
    # HARNESS first: parser/policy/store faults can masquerade as anything.
    ("PACKAGE_LOCK_MALFORMED_PARSER", "HARNESS"),
    ("EVIDENCE_STORE_UNAVAILABLE", "HARNESS"),
    ("COMMAND_WORKER_LOST", "HARNESS"),
    ("DISPOSABLE_GENERATION_CONTAMINATED", "HARNESS"),
    ("FILESYSTEM_PLATFORM_FAILURE", "HARNESS"),
    # RUNTIME/toolchain identity faults.
    ("ANGULAR_CLI_AUTHORITY_MISMATCH", "RUNTIME"),
    ("ANGULAR_CLI_DELEGATION_UNPROVEN", "RUNTIME"),
    ("CHILD_PACKAGE_MANAGER_AUTHORITY_MISMATCH", "RUNTIME"),
    ("GOVERNED_PATH_DRIFT", "RUNTIME"),
    ("RUNTIME_DESCRIPTOR_MISMATCH", "RUNTIME"),
    ("ENGINES_INCOMPATIBLE", "RUNTIME"),
    # LOCKFILE authority/root-sync/convergence faults.
    ("PACKAGE_LOCK_MISSING", "LOCKFILE"),
    ("SHRINKWRAP_UNSUPPORTED_BY_NPM", "LOCKFILE"),
    ("SHRINKWRAP_POLICY_DECISION_REQUIRED", "LOCKFILE"),
    ("LOCK_CONVERGENCE_EXHAUSTED", "LOCKFILE"),
    ("LOCK_SCHEMA_TRANSITION_INVALID", "LOCKFILE"),
    ("NPM_CI_REJECTED_CONVERGED_LOCK", "LOCKFILE"),
    ("ROOT_SYNC_REQUIRED_MISMATCH", "LOCKFILE"),
    # DEPENDENCY solver-owned outcomes.
    ("ETARGET", "DEPENDENCY"),
    ("PEER_CONFLICT_FROM_NPM", "DEPENDENCY"),
    ("NPM_SOLVER_FAILURE", "DEPENDENCY"),
    ("NPM_TREE_INVALID", "DEPENDENCY"),
)

#: Classifications that must NEVER route to source repair.
NON_SOURCE_REPAIR_PHASES = frozenset({"HARNESS", "RUNTIME", "DEPENDENCY", "LOCKFILE"})


def classify_failure_owner(
    *,
    phase_hint: str | None,
    failure_codes: tuple[str, ...],
) -> tuple[FailurePhase, FailureOwner, str]:
    """Deterministic phase/owner routing from structured evidence codes.

    Returns ``(phase, owner, primary_code)``.  Explicit ``phase_hint`` wins
    when it carries a proven phase; otherwise the first matching evidence
    prefix decides; anything else routes MAIN_REPAIR with low-confidence
    human-escalation semantics preserved upstream.
    """
    proven_phases = {"HARNESS", "RUNTIME", "DEPENDENCY", "LOCKFILE", "DETERMINISTIC_SOURCE", "MAIN_REPAIR"}
    if phase_hint in proven_phases:
        return phase_hint, PHASE_OWNERS[phase_hint], failure_codes[0] if failure_codes else ""
    for code in failure_codes:
        for prefix, phase in _PHASE_EVIDENCE_PREFIXES:
            if code.startswith(prefix):
                return phase, PHASE_OWNERS[phase], code
    return "MAIN_REPAIR", "MAIN_REPAIR_LLM", failure_codes[0] if failure_codes else ""
