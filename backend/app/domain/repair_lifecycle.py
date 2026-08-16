"""Deterministic repair lifecycle state machine (V2 F04).

Codifies the repair attempt status vocabulary, legal transitions, terminal
sealing, and restart-recovery mapping so repair state handling is deterministic
and verifiable.  Pure domain: no process, filesystem, database, or network side
effects.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class RepairLifecycleStatus(str, Enum):
    """Authoritative repair attempt lifecycle vocabulary."""

    PENDING = "pending"
    PROPOSING = "proposing"
    PROPOSED = "proposed"
    EVIDENCE_FROZEN = "evidence_frozen"
    WAITING_G10 = "waiting_g10"
    REQUEST_CHANGES = "request_changes"
    WAITING_REPAIR_REVISION = "waiting_repair_revision"
    APPLIED = "applied"
    APPLIED_VERIFIED = "applied_verified"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    FAILED = "failed"
    COMPLETED = "completed"


#: States a repair may legitimately occupy (superset of transitions observed).
ALL_LIFECYCLE_STATUSES = frozenset(status.value for status in RepairLifecycleStatus)

#: In-flight states bound to a live worker/LLM step; a restart mid-step strands them.
IN_FLIGHT_STATUSES = frozenset(
    {
        RepairLifecycleStatus.PENDING.value,
        RepairLifecycleStatus.PROPOSING.value,
        RepairLifecycleStatus.PROPOSED.value,
        RepairLifecycleStatus.EVIDENCE_FROZEN.value,
    }
)

#: Terminal, sealed states.  Once a lifecycle reaches a sealed state, no further
#: mutation is allowed (F04-04).
SEALED_TERMINAL_STATUSES = frozenset(
    {
        RepairLifecycleStatus.APPLIED.value,
        RepairLifecycleStatus.APPLIED_VERIFIED.value,
        RepairLifecycleStatus.SUPERSEDED.value,
        RepairLifecycleStatus.REJECTED.value,
        RepairLifecycleStatus.FAILED.value,
        RepairLifecycleStatus.COMPLETED.value,
    }
)

#: Deterministic restart-recovery target for each stranded in-flight state.
#: Repairs that can be re-driven from persisted evidence resume at their evidence
#: checkpoint; a stranded pre-evidence proposal resumes as pending.
_RESTART_RECOVERY_MAP = {
    RepairLifecycleStatus.PENDING.value: RepairLifecycleStatus.PENDING.value,
    RepairLifecycleStatus.PROPOSING.value: RepairLifecycleStatus.PENDING.value,
    RepairLifecycleStatus.PROPOSED.value: RepairLifecycleStatus.EVIDENCE_FROZEN.value,
    RepairLifecycleStatus.EVIDENCE_FROZEN.value: RepairLifecycleStatus.EVIDENCE_FROZEN.value,
}

#: Legal forward transitions between lifecycle states.
_TRANSITIONS: dict[str, frozenset[str]] = {
    RepairLifecycleStatus.PENDING.value: frozenset({RepairLifecycleStatus.PROPOSING.value, RepairLifecycleStatus.FAILED.value, RepairLifecycleStatus.SUPERSEDED.value}),
    RepairLifecycleStatus.PROPOSING.value: frozenset({RepairLifecycleStatus.PROPOSED.value, RepairLifecycleStatus.FAILED.value, RepairLifecycleStatus.SUPERSEDED.value}),
    RepairLifecycleStatus.PROPOSED.value: frozenset({RepairLifecycleStatus.EVIDENCE_FROZEN.value, RepairLifecycleStatus.REQUEST_CHANGES.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.FAILED.value}),
    RepairLifecycleStatus.EVIDENCE_FROZEN.value: frozenset({RepairLifecycleStatus.WAITING_G10.value, RepairLifecycleStatus.REQUEST_CHANGES.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.FAILED.value}),
    RepairLifecycleStatus.WAITING_G10.value: frozenset({RepairLifecycleStatus.APPLIED.value, RepairLifecycleStatus.REQUEST_CHANGES.value, RepairLifecycleStatus.REJECTED.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.FAILED.value}),
    RepairLifecycleStatus.REQUEST_CHANGES.value: frozenset({RepairLifecycleStatus.WAITING_REPAIR_REVISION.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.FAILED.value}),
    RepairLifecycleStatus.WAITING_REPAIR_REVISION.value: frozenset({RepairLifecycleStatus.PROPOSING.value, RepairLifecycleStatus.SUPERSEDED.value, RepairLifecycleStatus.FAILED.value}),
    RepairLifecycleStatus.APPLIED.value: frozenset({RepairLifecycleStatus.APPLIED_VERIFIED.value, RepairLifecycleStatus.FAILED.value}),
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


def restart_recovery_target(status: str | None) -> str | None:
    """Deterministic restart-recovery mapping for a stranded in-flight attempt.

    Returns the resumable status to transition to, or None when the status is
    not an in-flight state (terminal/sealed states are untouched).
    """
    if status is None or is_sealed(status):
        return None
    return _RESTART_RECOVERY_MAP.get(status)
