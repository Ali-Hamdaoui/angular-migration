"""Deterministic repair lifecycle state machine (V2 F04).

Codifies the repair attempt status vocabulary as actually used by the
repository (``repair_application_service.py``, ``transformer_graph.py``,
``stage_gate_service.py``), the legal forward transitions, and the conservative
sealed set.  Pure domain: no process, filesystem, database, or network side
effects.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class RepairLifecycleStatus(str, Enum):
    """Authoritative repair attempt lifecycle vocabulary (repository truth)."""

    EVIDENCE_FROZEN = "evidence_frozen"
    PROPOSED = "proposed"
    REVIEW_ACCEPTED = "review_accepted"
    REQUEST_CHANGES = "request_changes"
    WAITING_G10 = "waiting_g10"
    APPROVED_PENDING_EXECUTION = "approved_pending_execution"
    EXECUTING = "executing"
    APPLYING = "applying"
    APPLIED = "applied"
    APPLIED_VERIFIED = "applied_verified"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    MIGRATION_RETRIED = "migration_retried"
    REVALIDATING = "revalidating"
    REVALIDATING_AFFECTED = "revalidating_affected"
    WAITING_G11 = "waiting_g11"
    APPLY_FAILED = "apply_failed"
    APPLY_RECOVERY_REQUIRED = "apply_recovery_required"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    # V2.2 P1-1: bounded fourth reviewer outcome; evidence acquisition or a
    # governed human route follows, never silent acceptance.
    REVIEW_INSUFFICIENT_CONTEXT = "review_insufficient_context"


ALL_LIFECYCLE_STATUSES = frozenset(status.value for status in RepairLifecycleStatus)

#: Worker-bound in-flight states strandable by a restart.  These are the states
#: the startup sweep considers for deterministic recovery.
IN_FLIGHT_STATUSES = frozenset(
    {
        RepairLifecycleStatus.EVIDENCE_FROZEN.value,
        RepairLifecycleStatus.PROPOSED.value,
        RepairLifecycleStatus.REVIEW_ACCEPTED.value,
        RepairLifecycleStatus.WAITING_G10.value,
        RepairLifecycleStatus.APPROVED_PENDING_EXECUTION.value,
        RepairLifecycleStatus.EXECUTING.value,
        RepairLifecycleStatus.APPLYING.value,
    }
)

#: Conservative sealed set: states with no observed outgoing transition in the
#: repository flow.  Deliberately minimal so the sealing guard can never block a
#: transition the real workflow legitimately makes.
SEALED_TERMINAL_STATUSES = frozenset(
    {
        RepairLifecycleStatus.SUPERSEDED.value,
        RepairLifecycleStatus.REJECTED.value,
        RepairLifecycleStatus.CANCELLED.value,
    }
)

#: Legal forward transitions, derived from actual assignment sites.
_TRANSITIONS: dict[str, frozenset[str]] = {
    RepairLifecycleStatus.EVIDENCE_FROZEN.value: frozenset({RepairLifecycleStatus.PROPOSED.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.PROPOSED.value: frozenset({RepairLifecycleStatus.REVIEW_ACCEPTED.value, RepairLifecycleStatus.REQUEST_CHANGES.value, RepairLifecycleStatus.REVIEW_INSUFFICIENT_CONTEXT.value, RepairLifecycleStatus.REJECTED.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.REVIEW_INSUFFICIENT_CONTEXT.value: frozenset({RepairLifecycleStatus.PROPOSED.value, RepairLifecycleStatus.REJECTED.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.REVIEW_ACCEPTED.value: frozenset({RepairLifecycleStatus.WAITING_G10.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.REQUEST_CHANGES.value: frozenset({RepairLifecycleStatus.REJECTED.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.WAITING_G10.value: frozenset({RepairLifecycleStatus.APPROVED_PENDING_EXECUTION.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.APPROVED_PENDING_EXECUTION.value: frozenset({RepairLifecycleStatus.EXECUTING.value, RepairLifecycleStatus.APPLIED_VERIFIED.value, RepairLifecycleStatus.APPLY_FAILED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.EXECUTING.value: frozenset({RepairLifecycleStatus.APPLIED_VERIFIED.value, RepairLifecycleStatus.APPLY_FAILED.value, RepairLifecycleStatus.APPLY_RECOVERY_REQUIRED.value, RepairLifecycleStatus.VALIDATION_FAILED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.APPLYING.value: frozenset({RepairLifecycleStatus.APPLIED_VERIFIED.value, RepairLifecycleStatus.APPLY_FAILED.value, RepairLifecycleStatus.APPLY_RECOVERY_REQUIRED.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.APPLIED.value: frozenset({RepairLifecycleStatus.REVALIDATING.value, RepairLifecycleStatus.REVALIDATING_AFFECTED.value, RepairLifecycleStatus.WAITING_G11.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.APPLIED_VERIFIED.value: frozenset({RepairLifecycleStatus.MIGRATION_RETRIED.value, RepairLifecycleStatus.REVALIDATING.value, RepairLifecycleStatus.REVALIDATING_AFFECTED.value, RepairLifecycleStatus.WAITING_G11.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.VALIDATION_PASSED.value: frozenset({RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.VALIDATION_FAILED.value: frozenset({RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.MIGRATION_RETRIED.value: frozenset({RepairLifecycleStatus.REVALIDATING.value, RepairLifecycleStatus.REVALIDATING_AFFECTED.value, RepairLifecycleStatus.WAITING_G11.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.REVALIDATING.value: frozenset({RepairLifecycleStatus.WAITING_G11.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.REVALIDATING_AFFECTED.value: frozenset({RepairLifecycleStatus.REVALIDATING.value, RepairLifecycleStatus.WAITING_G11.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.WAITING_G11.value: frozenset({RepairLifecycleStatus.VALIDATION_PASSED.value, RepairLifecycleStatus.VALIDATION_FAILED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.APPLY_FAILED.value: frozenset({RepairLifecycleStatus.APPLY_RECOVERY_REQUIRED.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.CANCELLED.value}),
    RepairLifecycleStatus.APPLY_RECOVERY_REQUIRED.value: frozenset({RepairLifecycleStatus.EXECUTING.value, RepairLifecycleStatus.APPLIED_VERIFIED.value, RepairLifecycleStatus.CANCELLED.value}),
}


class RepairLifecycleTransition(BaseModel):
    """Result of evaluating a lifecycle transition request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_id: str
    from_status: str
    to_status: str
    allowed: bool
    reason: str | None = None
    sealed: bool = False


def is_sealed(status: str | None) -> bool:
    return status in SEALED_TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# V2.2 P1-1 — candidate-scoped repair intent boundaries.
# ---------------------------------------------------------------------------

#: Files a repair proposal may never touch, in any candidate.
REPAIR_FORBIDDEN_PATHS = frozenset({"package-lock.json", "npm-shrinkwrap.json"})


class RepairScopeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def assert_repair_candidate_scope(
    *,
    touched_paths: tuple[str, ...],
    candidate_root_prefix: str,
    allowed_paths: tuple[str, ...] | None = None,
) -> None:
    """Fail closed unless every touched path stays inside the isolated candidate.

    Rejects absolute paths, parent traversal, lockfile authority files, and —
    when an explicit allowlist is bound — anything outside it.  ``None`` as a
    path or root is invalid; the authoritative generation can never be the
    application target because its prefix never matches.
    """
    if not candidate_root_prefix:
        raise RepairScopeError("REPAIR_CANDIDATE_ROOT_REQUIRED", "repair application requires a bound candidate root")
    allowed = {path.replace("\\", "/") for path in allowed_paths} if allowed_paths is not None else None
    for raw in touched_paths:
        if not isinstance(raw, str) or not raw:
            raise RepairScopeError("REPAIR_PATH_INVALID", "repair operation paths must be non-empty strings")
        path = raw.replace("\\", "/")
        if path.startswith(("/", "~")) or (len(path) > 1 and path[1] == ":"):
            raise RepairScopeError("REPAIR_PATH_ABSOLUTE", f"repair path must be relative to the candidate: {raw!r}")
        if path.startswith("./"):
            path = path[2:]
        normalized = path.lstrip("/") if path.startswith("/") else path
        if ".." in normalized.split("/"):
            raise RepairScopeError("REPAIR_PATH_TRAVERSAL", f"repair path escapes the candidate root: {raw!r}")
        if normalized in REPAIR_FORBIDDEN_PATHS or normalized.endswith("/" + next(iter(REPAIR_FORBIDDEN_PATHS))) or any(normalized == forbidden or normalized.endswith("/" + forbidden) for forbidden in REPAIR_FORBIDDEN_PATHS):
            raise RepairScopeError("REPAIR_LOCK_AUTHORITY_FORBIDDEN", f"repair proposals cannot edit {normalized!r}")
        if allowed is not None and normalized not in allowed:
            raise RepairScopeError("REPAIR_PATH_OUT_OF_SCOPE", f"repair path is outside the bounded problem group: {normalized!r}")
    return


def can_transition(from_status: str | None, to_status: str | None) -> bool:
    if from_status is None or to_status is None:
        return False
    return to_status in _TRANSITIONS.get(from_status, frozenset())


def evaluate_transition(attempt_id: str, from_status: str | None, to_status: str) -> RepairLifecycleTransition:
    """Evaluate a transition, enforcing the state machine and sealing rules."""
    if is_sealed(from_status):
        return RepairLifecycleTransition(
            attempt_id=attempt_id, from_status=from_status or "", to_status=to_status,
            allowed=False, sealed=True, reason="repair lifecycle is sealed; no further mutation is allowed",
        )
    if from_status not in ALL_LIFECYCLE_STATUSES or to_status not in ALL_LIFECYCLE_STATUSES:
        return RepairLifecycleTransition(
            attempt_id=attempt_id, from_status=from_status or "", to_status=to_status,
            allowed=False, reason="unknown lifecycle status",
        )
    if not can_transition(from_status, to_status):
        return RepairLifecycleTransition(
            attempt_id=attempt_id, from_status=from_status or "", to_status=to_status,
            allowed=False, reason=f"illegal transition from {from_status} to {to_status}",
        )
    return RepairLifecycleTransition(
        attempt_id=attempt_id, from_status=from_status or "", to_status=to_status,
        allowed=True, reason="legal lifecycle transition",
    )
