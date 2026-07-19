"""Domain models for G07 — patch preflight, G11 gate, and repair validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PreflightStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class G11Decision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"
    EXPIRED = "EXPIRED"
    STALE = "STALE"


class G11GateStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"
    EXPIRED = "expired"
    MODIFICATION_REQUESTED = "modification_requested"


class RepairValidationStatus(str, Enum):
    NOT_STARTED = "not_started"
    PREFLIGHT_RUNNING = "preflight_running"
    PREFLIGHT_COMPLETED = "preflight_completed"
    PREFLIGHT_FAILED = "preflight_failed"
    VALIDATION_RUNNING = "validation_running"
    VALIDATION_COMPLETED = "validation_completed"
    VALIDATION_FAILED = "validation_failed"
    WAITING_G11 = "waiting_g11"
    G11_PASSED = "g11_passed"
    G11_REJECTED = "g11_rejected"


@dataclass(frozen=True)
class PreflightCheck:
    check_name: str
    passed: bool
    detail: str = ""
    severity: str = "error"


@dataclass(frozen=True)
class PatchPreflightReport:
    preflight_id: str
    attempt_id: str
    run_id: str
    status: PreflightStatus
    profile_match: bool = True
    plan_version_match: bool = True
    checks: tuple[PreflightCheck, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime | None = None


@dataclass(frozen=True)
class InvalidationBoundary:
    validation_run_id: str
    invalidated_steps: tuple[str, ...] = ()
    earliest_invalidated_step: str = ""
    reason: str = ""
    boundary_checksum: str = ""


@dataclass(frozen=True)
class ErrorDelta:
    previous_errors: tuple[str, ...] = ()
    current_errors: tuple[str, ...] = ()
    new_errors: tuple[str, ...] = ()
    resolved_errors: tuple[str, ...] = ()
    persistent_errors: tuple[str, ...] = ()
    delta_checksum: str = ""


@dataclass(frozen=True)
class ValidationRerunReference:
    rerun_id: str
    run_id: str
    stage_id: str
    attempt_id: str
    profile_id: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    passed: bool = False
    logs_ref: str = ""
    results_ref: str = ""


@dataclass(frozen=True)
class G11Package:
    gate_id: str
    run_id: str
    attempt_id: str
    state_version: int
    artifact_set_checksum: str
    plan_version: str = ""
    workspace_fingerprint: str = ""
    preflight_report_ref: str = ""
    validation_summary_ref: str = ""
    error_delta_ref: str = ""
    rerun_ref: str = ""
    decision: G11Decision = G11Decision.PENDING
    bound_checksum: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True)
class G11GateRecord:
    gate_id: str
    run_id: str
    attempt_id: str
    status: G11GateStatus
    state_version: int
    artifact_set_checksum: str
    plan_version: str = ""
    workspace_fingerprint: str = ""
    decision: G11Decision = G11Decision.PENDING
    decision_at: datetime | None = None
    actor: str = ""
    rationale: str = ""
    bound_checksum: str = ""
    stale_replay: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RepairValidationResult:
    attempt_id: str
    run_id: str
    status: RepairValidationStatus
    state_version: int
    preflight_report: PatchPreflightReport | None = None
    invalidation_boundary: InvalidationBoundary | None = None
    error_delta: ErrorDelta | None = None
    rerun_reference: ValidationRerunReference | None = None
    g11_package: G11Package | None = None
    g11_record: G11GateRecord | None = None
    artifact_refs: dict[str, str] = field(default_factory=dict)
    failure_evidence: dict[str, Any] | None = None
    idempotent_replay: bool = False
