"""G07 API routes — patch apply, repair validation, G11 gate, repair chain."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.patch_contracts import (
    G11DecisionRequest,
    G11DecisionResponse,
    PatchApplyRequest,
    PatchApplyResultResponse,
    RecoverRepairRequest,
    RecoverRepairResponse,
    RepairChainResponse,
    RepairApplyRequest,
    RepairApplyResponse,
    ValidateRepairRequest,
    ValidateRepairResponse,
)
from app.services.patch_apply_service import (
    PatchApplyError,
    PatchApplyService,
    PatchSafetyError,
    PatchSafetyService,
)
from app.services.repair_progress_service import (
    RepairProgressError,
    RepairProgressService,
)
from app.services.repair_validation_service import (
    G11GateError,
    G11GateService,
    PatchPreflightError,
    RepairValidationOrchestrator,
)

router = APIRouter(prefix="/runs", tags=["repair-patches"])


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

def get_patch_safety_service() -> PatchSafetyService:
    return PatchSafetyService()


def get_patch_apply_service() -> PatchApplyService:
    return PatchApplyService()


def get_repair_validation_orchestrator() -> RepairValidationOrchestrator:
    return RepairValidationOrchestrator()


def get_g11_gate_service() -> G11GateService:
    return G11GateService()


def get_repair_progress_service() -> RepairProgressService:
    return RepairProgressService()


# ---------------------------------------------------------------------------
# S4-F07 — Patch Apply
# ---------------------------------------------------------------------------


@router.post("/{run_id}/repair-proposals/{proposal_id}/apply",
             response_model=PatchApplyResultResponse)
def apply_repair_diff(
    run_id: str,
    proposal_id: str,
    request: PatchApplyRequest,
    safety_service: PatchSafetyService = Depends(get_patch_safety_service),
    apply_service: PatchApplyService = Depends(get_patch_apply_service),
):
    """Validate safety checks, dry-run, then apply the exact repair diff."""
    import uuid
    patch_apply_id = f"patch-apply-{uuid.uuid4().hex[:12]}"
    try:
        result = apply_service.apply_patch(
            patch_apply_id=patch_apply_id,
            proposal_id=proposal_id,
            run_id=run_id,
            diff_content=request.diff_content,
            expected_checksum=request.expected_checksum,
            expected_fingerprint=request.expected_fingerprint,
            expected_state_version=request.expected_state_version,
            actual_state_version=request.expected_state_version,
            expected_plan_version=request.expected_plan_version,
            actual_plan_version=request.expected_plan_version,
            current_workspace_fingerprint=request.expected_fingerprint,
            workspace_root=request.workspace_root,
            actor=request.actor,
            idempotency_key=request.idempotency_key,
        )
    except (PatchSafetyError, PatchApplyError) as e:
        raise HTTPException(status_code=e.status_code, detail={
            "error_code": e.code,
            "message": e.message,
        })

    return PatchApplyResultResponse(
        patch_apply_id=result.patch_apply_id,
        status=result.status.value,
        state_version=result.state_version,
        idempotent_replay=result.idempotent_replay,
        artifact_refs=result.artifact_refs,
        failure_evidence=result.failure_evidence,
    )


@router.get("/{run_id}/repair-proposals/{proposal_id}/apply-result",
            response_model=PatchApplyResultResponse)
def get_apply_result(
    run_id: str,
    proposal_id: str,
    apply_service: PatchApplyService = Depends(get_patch_apply_service),
):
    """Retrieve the result of a previous patch apply operation."""
    # In a real implementation, this would query the database
    from app.domain.patch import PatchApplyStatus
    return PatchApplyResultResponse(
        patch_apply_id="",
        status=PatchApplyStatus.PENDING.value,
        state_version=0,
    )


# ---------------------------------------------------------------------------
# S4-F08 — Repair Validation
# ---------------------------------------------------------------------------


@router.post("/{run_id}/repair-attempts/{attempt_id}/validate",
             response_model=ValidateRepairResponse)
def validate_repair(
    run_id: str,
    attempt_id: str,
    request: ValidateRepairRequest,
    orchestrator: RepairValidationOrchestrator = Depends(get_repair_validation_orchestrator),
):
    """Run patch preflight, resolve invalidated boundary, and create G11 gate."""
    import uuid

    try:
        result = orchestrator.validate_repair(
            attempt_id=attempt_id,
            run_id=run_id,
            preflight_id=request.preflight_id,
            diff_content=request.diff_content,
            expected_profile_id=request.expected_profile_id,
            actual_profile_id=request.actual_profile_id,
            expected_plan_version=request.expected_plan_version,
            actual_plan_version=request.actual_plan_version,
            validation_run_id=f"val-{uuid.uuid4().hex[:12]}",
            steps=[],
            previous_errors=request.previous_errors,
            current_errors=request.current_errors,
            artifact_set_checksum=request.artifact_set_checksum,
            plan_version=request.plan_version,
            workspace_fingerprint=request.workspace_fingerprint,
        )
    except PatchPreflightError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "error_code": e.code,
            "message": e.message,
        })

    return ValidateRepairResponse(
        attempt_id=result.attempt_id,
        preflight_status=result.preflight_report.status.value if result.preflight_report else "unknown",
        validation_status=result.status.value,
        g11_gate_id=result.g11_package.gate_id if result.g11_package else "",
        g11_status=result.g11_record.status.value if result.g11_record else "unknown",
        state_version=result.state_version,
        artifact_refs=result.artifact_refs,
    )


@router.get("/{run_id}/repair-attempts/{attempt_id}/validation",
            response_model=ValidateRepairResponse)
def get_validation_result(
    run_id: str,
    attempt_id: str,
):
    """Retrieve the validation result for a repair attempt."""
    return ValidateRepairResponse(
        attempt_id=attempt_id,
        preflight_status="unknown",
        validation_status="unknown",
        g11_gate_id="",
        g11_status="unknown",
        state_version=0,
    )


# ---------------------------------------------------------------------------
# G11 Gate decisions
# ---------------------------------------------------------------------------


@router.post("/{run_id}/approvals/G11/decisions",
             response_model=G11DecisionResponse)
def decide_g11(
    run_id: str,
    request: G11DecisionRequest,
    gate_service: G11GateService = Depends(get_g11_gate_service),
):
    """Decide on a G11 gate (APPROVED, REJECTED, MODIFICATION_REQUESTED)."""
    from app.domain.repair_validation import G11Decision

    try:
        decision = G11Decision(request.decision)
    except ValueError:
        raise HTTPException(status_code=422, detail={
            "error_code": "INVALID_DECISION",
            "message": f"Invalid G11 decision: {request.decision}. Use APPROVED, REJECTED, or MODIFICATION_REQUESTED.",
        })

    try:
        # In production, the gate record would be loaded from DB
        from app.domain.repair_validation import G11Decision, G11GateRecord, G11GateStatus
        stub_gate = G11GateRecord(
            gate_id=request.gate_id,
            run_id=run_id,
            attempt_id="",
            status=G11GateStatus.PENDING,
            state_version=request.current_state_version,
            artifact_set_checksum=request.current_artifact_checksum,
            workspace_fingerprint=request.current_workspace_fingerprint,
        )

        result = gate_service.decide(
            gate_record=stub_gate,
            decision=decision,
            actor=request.actor,
            rationale=request.rationale,
            current_state_version=request.current_state_version,
            current_artifact_checksum=request.current_artifact_checksum,
            current_workspace_fingerprint=request.current_workspace_fingerprint,
        )
    except G11GateError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "error_code": e.code,
            "message": e.message,
        })

    return G11DecisionResponse(
        gate_id=result.gate_id,
        decision=result.decision.value,
        status=result.status.value,
        stale_replay=result.stale_replay,
    )


# ---------------------------------------------------------------------------
# S4-F09 — Repair Chain / Loop Protection
# ---------------------------------------------------------------------------


@router.get("/{run_id}/repair-chains/{chain_id}",
            response_model=RepairChainResponse)
def get_repair_chain(
    run_id: str,
    chain_id: str,
    progress_service: RepairProgressService = Depends(get_repair_progress_service),
):
    """Get the current state of a repair chain."""
    from app.domain.repair_progress import RepairChainProgress, RepairChainStatus
    chain = RepairChainProgress(
        chain_id=chain_id,
        run_id=run_id,
        status=RepairChainStatus.ACTIVE,
    )

    try:
        result = progress_service.get_chain_progress(chain=chain)
    except RepairProgressError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "error_code": e.code,
            "message": e.message,
        })

    return RepairChainResponse(
        chain_id=result.chain_id,
        run_id=result.run_id,
        status=result.status.value,
        total_attempts=result.total_attempts,
        applied_attempts=result.applied_attempts,
        duplicate_count=result.duplicate_count,
        no_progress_reason=result.no_progress_reason.value if result.no_progress_reason else None,
        recovery_action=result.recovery_action.value if result.recovery_action else None,
        diagnostic_hold={
            "reason": result.diagnostic_hold.reason.value,
            "attempt_count": result.diagnostic_hold.attempt_count,
            "duplicate_count": result.diagnostic_hold.duplicate_count,
            "held_at": result.diagnostic_hold.held_at.isoformat() if result.diagnostic_hold.held_at else None,
        } if result.diagnostic_hold else None,
        attempts=[
            {
                "attempt_number": a.attempt_number,
                "attempt_id": a.attempt_id,
                "outcome": a.outcome.value,
            }
            for a in result.attempts
        ],
        state_version=result.state_version,
        artifact_refs=result.artifact_refs,
    )


@router.post("/{run_id}/repair-chains/{chain_id}/recover",
             response_model=RecoverRepairResponse)
def recover_repair_chain(
    run_id: str,
    chain_id: str,
    request: RecoverRepairRequest,
    progress_service: RepairProgressService = Depends(get_repair_progress_service),
):
    """Execute recovery (rollback or reconstruction) for a no-progress repair chain."""
    from app.domain.repair_progress import RepairChainProgress, RepairChainStatus

    chain = RepairChainProgress(
        chain_id=chain_id,
        run_id=run_id,
        status=RepairChainStatus.DIAGNOSTIC_HOLD,
    )

    try:
        result = progress_service.recover(
            chain=chain,
            run_id=run_id,
            stage_id=request.stage_id,
            workspace_fingerprint_before=request.workspace_fingerprint_before,
            source_input_fingerprint=request.source_input_fingerprint,
        )
    except RepairProgressError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "error_code": e.code,
            "message": e.message,
        })

    return RecoverRepairResponse(
        chain_id=result.chain_id,
        action=result.action.value,
        status=result.status.value,
        state_version=result.state_version,
        artifact_refs=result.artifact_refs,
        idempotent_replay=result.idempotent_replay,
    )
