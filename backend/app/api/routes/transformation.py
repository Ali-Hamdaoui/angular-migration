"""Read and cancel the authoritative Transformer workflow."""

from pathlib import Path
import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.authentication import authenticated_actor, authorize_run
from app.api.errors import error_response
from app.domain.transformation import (
    RepairDecisionRequest,
    RepairRevisionRequest,
    StageGateDecisionRequest,
    TransformationCancelRequest,
    TransformationRestartRequest,
)
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationStageModel,
    MigrationRunModel,
    RepairAttemptModel,
    LlmInvocationModel,
    StageCheckpointModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StagePromptRequestModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.transformation_continuation_service import (
    TransformationContinuationError,
    TransformationContinuationService,
)
from app.services.stage_gate_service import StageGateError, StageGateService
from app.services.command_executor_service import CommandExecutorService
from app.services.repair_application_service import RepairApplicationError, RepairApplicationService
from app.artifact_store import ArtifactNotFoundError, ArtifactStoreError, LocalFilesystemArtifactStore
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_prompt_service import TransformerPromptError, TransformerPromptService
from app.services.transformer_stage_service import TransformerStageService
from app.domain.transformation import PromptDecisionRequest

router = APIRouter(prefix="/runs", tags=["transformation"])


def _artifact_content(session, run_id: str, artifact_id: str | None):
    if not artifact_id:
        return None
    run = session.get(MigrationRunModel, run_id)
    metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
    if run is None or metadata is None or metadata.run_id != run_id:
        return None
    try:
        stored = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        ).read_artifact(run_id, metadata.relative_path)
    except (ArtifactNotFoundError, ArtifactStoreError, OSError):
        return None
    if stored.ref.artifact_id != artifact_id or stored.ref.checksum != metadata.checksum:
        return None
    return stored.content


_NODE_ACTION_LABELS = {
    "validate_g06": "Accepting G06 stage approval",
    "prepare_workspace": "Preparing the governed stage workspace",
    "resolve_runtime": "Resolving the runtime profile",
    "dependency_preflight": "Running dependency preflight",
    "collect_known_decisions": "Collecting known stage decisions",
    "create_g07": "Preparing G07 stage approval",
    "bootstrap_install": "Running bootstrap install",
    "verify_bootstrap": "Verifying bootstrap install",
    "angular_update": "Running Angular migration update",
    "handle_prompt": "Handling Angular CLI prompt",
    "target_inspection": "Verifying target Angular version",
    "version_verify": "Verifying target Angular version",
    "final_install": "Running final install",
    "build": "Running build validation",
    "test": "Running test validation",
    "aggregate_validation": "Aggregating validation evidence",
    "classify_failure": "Classifying failure evidence",
    "propose_repair": "Running repair proposal",
    "review_repair": "Reviewing proposal",
    "create_g10": "Preparing G10 repair approval",
    "apply_repair": "Applying approved repair",
    "angular_update_retry": "Retrying Angular migration",
    "lockfile_generation": "Regenerating the npm lockfile",
    "repair_revalidate": "Revalidating after repair",
    "create_g11": "Preparing G11 revalidation approval",
    "create_g09": "Preparing G09 validation approval",
    "create_g12": "Preparing G12 approval",
    "seal_stage": "Sealing the stage",
    "materialize_next_stage": "Materializing the next stage",
    "complete_run": "Completing the migration run",
}


def _next_backend_action(continuation) -> str | None:
    if continuation.status == "waiting_command":
        return "Command in flight"
    if continuation.status == "waiting_gate":
        return "Waiting for human gate approval"
    if continuation.status == "waiting_prompt":
        return "Waiting for CLI prompt decision"
    if continuation.status == "waiting_repair_revision":
        return "Waiting for human revision instruction"
    if continuation.status == "waiting_retry":
        return "Waiting for the governed retry window"
    if continuation.status == "blocked" or continuation.status == "failed":
        return "Blocked"
    if continuation.status == "completed":
        return "Completed"
    return _NODE_ACTION_LABELS.get(continuation.current_node)


def _projection(session, continuation: TransformationContinuationModel) -> dict[str, object]:
    stage = session.get(MigrationStageModel, continuation.current_stage_id)
    route_stages = list(
        session.scalars(
            select(MigrationStageModel)
            .where(MigrationStageModel.run_id == continuation.run_id)
            .order_by(MigrationStageModel.stage_order)
        )
    )
    checkpoint = session.scalar(
        select(StageCheckpointModel)
        .where(StageCheckpointModel.stage_id == continuation.current_stage_id)
        .order_by(StageCheckpointModel.sequence.desc())
        .limit(1)
    )
    command = session.scalar(
        select(CommandExecutionModel)
        .where(
            CommandExecutionModel.run_id == continuation.run_id,
            CommandExecutionModel.status.in_(("queued", "pending", "running")),
        )
        .order_by(CommandExecutionModel.requested_at.desc())
        .limit(1)
    )
    if command is None and continuation.waiting_execution_id:
        waited = session.get(CommandExecutionModel, continuation.waiting_execution_id)
        if waited is not None and waited.run_id == continuation.run_id:
            command = waited
    if command is None:
        command = session.scalar(
            select(CommandExecutionModel)
            .where(CommandExecutionModel.run_id == continuation.run_id)
            .order_by(CommandExecutionModel.requested_at.desc())
            .limit(1)
        )
    gate = session.scalar(
        select(StageGatePackageModel)
        .where(
            StageGatePackageModel.stage_id == continuation.current_stage_id,
            StageGatePackageModel.status.in_(("pending", "approved", "rejected")),
        )
        .order_by(StageGatePackageModel.gate_version.desc())
        .limit(1)
    )
    prompt = session.scalar(
        select(StagePromptRequestModel)
        .where(
            StagePromptRequestModel.stage_id == continuation.current_stage_id,
            StagePromptRequestModel.status.not_in(("decided", "cancelled", "stale")),
        )
        .order_by(StagePromptRequestModel.created_at.desc())
        .limit(1)
    )
    explanation = (
        session.get(LlmInvocationModel, prompt.explanation_invocation_id)
        if prompt and prompt.explanation_invocation_id
        else None
    )
    repair = session.scalar(
        select(RepairAttemptModel)
        .where(
            RepairAttemptModel.run_id == continuation.run_id,
            RepairAttemptModel.stage_id == continuation.current_stage_id,
        )
        .order_by(RepairAttemptModel.attempt_number.desc())
        .limit(1)
    )
    safe_diff = None
    proposal = None
    review = None
    diff_metadata = None
    retry_execution = None
    if repair is not None:
        proposal_content = _artifact_content(session, continuation.run_id, repair.proposal_artifact_id)
        review_content = _artifact_content(session, continuation.run_id, repair.review_artifact_id)
        diff_metadata = session.scalar(
            select(ArtifactMetadataModel)
            .where(
                ArtifactMetadataModel.run_id == continuation.run_id,
                ArtifactMetadataModel.stage_id == continuation.current_stage_id,
                ArtifactMetadataModel.relative_path.like(
                    f"05_repairs/attempt-{repair.id}/candidate%.diff"
                ),
            )
            .order_by(ArtifactMetadataModel.created_at.desc())
            .limit(1)
        )
        safe_diff = _artifact_content(
            session,
            continuation.run_id,
            diff_metadata.id.removeprefix("metadata-") if diff_metadata else None,
        )
        try:
            proposal = json.loads(proposal_content) if proposal_content else None
            review = json.loads(review_content) if review_content else None
        except (TypeError, ValueError):
            proposal = None
            review = None
        angular_step = session.scalar(
            select(StageStepModel)
            .where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        retry_execution = (
            session.get(CommandExecutionModel, angular_step.execution_id)
            if angular_step is not None and angular_step.execution_id
            else None
        )
    latest_seal = session.scalar(
        select(StageCheckpointModel)
        .where(
            StageCheckpointModel.run_id == continuation.run_id,
            StageCheckpointModel.sealed.is_(True),
        )
        .order_by(StageCheckpointModel.created_at.desc())
        .limit(1)
    )
    runtime_profile_binding = (
        TransformerStageService.runtime_binding_evidence(session, continuation)[0]
        if continuation.last_error_code == "EXECUTION_PROFILE_STALE"
        else None
    )
    return {
        "run_id": continuation.run_id,
        "continuation_id": continuation.id,
        "stage_id": continuation.current_stage_id,
        "status": continuation.status,
        "current_node": continuation.current_node,
        "state_version": continuation.state_version,
        "stage_status": stage.status if stage else "missing",
        "source_version": stage.source_version_family if stage else None,
        "target_version": stage.target_version_family if stage else None,
        "checkpoint_kind": checkpoint.kind if checkpoint else None,
        "workspace_fingerprint": checkpoint.workspace_fingerprint if checkpoint else None,
        "active_gate": gate.gate_id if gate else None,
        "active_gate_package_checksum": gate.package_checksum if gate else None,
        "active_command_id": command.id if command else None,
        "active_command_status": command.status if command else None,
        "active_prompt_id": prompt.id if prompt else None,
        "active_prompt_checksum": prompt.prompt_checksum if prompt else None,
        "active_prompt_text": prompt.normalized_prompt if prompt else None,
        "active_prompt_options": [
            {"option_id": item["option_id"], "label": item["label"]}
            for item in (prompt.options_json if prompt else [])
        ],
        "active_prompt_explanation": (
            json.loads(explanation.redacted_summary)
            if explanation and explanation.redacted_summary
            else None
        ),
        "repair_attempt_id": repair.id if repair else None,
        "repair_attempt_number": repair.attempt_number if repair else None,
        "repair_parent_attempt_id": repair.parent_attempt_id if repair else None,
        "repair_status": repair.status if repair else None,
        "repair_risk_level": repair.risk_level if repair else None,
        "repair_proposal_checksum": repair.proposal_checksum if repair else None,
        "repair_review_checksum": repair.review_checksum if repair else None,
        "repair_proposal_id": repair.proposal_artifact_id if repair else None,
        "repair_base_checksum": repair.proposal_checksum if repair else None,
        "repair_diff_artifact_id": (
            diff_metadata.id.removeprefix("metadata-") if diff_metadata else None
        ),
        "repair_diff_checksum": diff_metadata.checksum if diff_metadata else None,
        "repair_proposal_operations": [
            {"operation": item.get("operation"), "path": item.get("path")}
            for item in (proposal.get("operations") or []) if proposal
        ],
        "repair_safe_diff": safe_diff,
        "repair_review": review,
        "repair_rationale": proposal.get("rationale", []) if proposal else [],
        "repair_apply_checksum": repair.apply_ledger_checksum if repair else None,
        "repair_validation_checksum": repair.validation_summary_checksum if repair else None,
        "next_backend_action": _next_backend_action(continuation),
        "angular_update_retry_attempt": (
            retry_execution.attempt_number if retry_execution else None
        ),
        "angular_update_retry_status": (
            retry_execution.status
            if retry_execution is not None
            and retry_execution.parent_execution_id is not None
            else None
        ),
        "route_stages": [
            {
                "stage_id": item.id,
                "source_version": item.source_version_family,
                "target_version": item.target_version_family,
                "status": item.status,
            }
            for item in route_stages
        ],
        "sealed_chain_hash": latest_seal.manifest_checksum if latest_seal else None,
        "last_error_code": continuation.last_error_code,
        "last_error_message": continuation.last_error_message,
        "runtime_profile_binding": runtime_profile_binding,
        "cancel_requested_at": continuation.cancel_requested_at,
    }


@router.get("/{run_id}/transformation")
def get_transformation(
    run_id: str,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        return _projection(session, continuation)


@router.post("/{run_id}/transformation/repairs/{attempt_id}/revisions")
def request_repair_revision(
    run_id: str,
    attempt_id: str,
    body: RepairRevisionRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    if body.attempt_id != attempt_id:
        return error_response(
            request,
            status_code=409,
            error_code="REPAIR_ATTEMPT_MISMATCH",
            message="Repair attempt path and payload do not match",
        )
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        attempt = session.get(RepairAttemptModel, attempt_id)
        if attempt is None or attempt.run_id != run_id:
            return error_response(
                request,
                status_code=404,
                error_code="REPAIR_ATTEMPT_NOT_FOUND",
                message="Repair attempt is missing",
            )
    try:
        return RepairApplicationService(scope=session_scope).request_revision(
            attempt_id=body.attempt_id,
            proposal_id=body.proposal_id,
            base_checksum=body.base_checksum,
            instruction=body.instruction,
            idempotency_key=body.idempotency_key,
            actor=actor,
        )
    except RepairApplicationError as error:
        return error_response(
            request,
            status_code=409,
            error_code=error.code,
            message=error.message,
        )


@router.post("/{run_id}/transformation/repairs/{attempt_id}/reject")
def reject_repair(
    run_id: str,
    attempt_id: str,
    body: RepairDecisionRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    if body.attempt_id != attempt_id:
        return error_response(
            request,
            status_code=409,
            error_code="REPAIR_ATTEMPT_MISMATCH",
            message="Repair attempt path and payload do not match",
        )
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        attempt = session.get(RepairAttemptModel, attempt_id)
        if attempt is None or attempt.run_id != run_id:
            return error_response(
                request,
                status_code=404,
                error_code="REPAIR_ATTEMPT_NOT_FOUND",
                message="Repair attempt is missing",
            )
    try:
        return RepairApplicationService(scope=session_scope).reject(
            attempt_id=body.attempt_id,
            proposal_id=body.proposal_id,
            base_checksum=body.base_checksum,
            idempotency_key=body.idempotency_key,
            actor=actor,
        )
    except RepairApplicationError as error:
        return error_response(
            request,
            status_code=409,
            error_code=error.code,
            message=error.message,
        )


@router.post("/{run_id}/transformation/prompts/{prompt_id}/decision")
def decide_prompt(
    run_id: str,
    prompt_id: str,
    body: PromptDecisionRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        try:
            prompt = TransformerPromptService().decide(
                session, continuation, prompt_id, body, actor=actor
            )
        except TransformerPromptError as error:
            return error_response(
                request,
                status_code=409,
                error_code=error.code,
                message=error.message,
            )
        return {
            "prompt_id": prompt.id,
            "selected_option_id": prompt.selected_option_id,
            "status": prompt.status,
            "state_version": continuation.state_version,
        }


@router.post("/{run_id}/transformation/gates/{gate_id}/decisions")
def decide_stage_gate(
    run_id: str,
    gate_id: str,
    body: StageGateDecisionRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if binding is None:
            return error_response(
                request,
                status_code=409,
                error_code="STAGE_WORKSPACE_MISSING",
                message="Prepared stage workspace binding is missing",
            )
        workspace_path = binding.workspace_path
        replay = session.scalar(
            select(StageGateDecisionModel.id).where(
                StageGateDecisionModel.run_id == run_id,
                StageGateDecisionModel.idempotency_key == body.idempotency_key,
            )
        ) is not None
    try:
        observed_fingerprint = StageSandboxCopier.fingerprint(Path(workspace_path))
    except OSError:
        return error_response(
            request,
            status_code=409,
            error_code="STAGE_WORKSPACE_MISSING",
            message="Prepared stage workspace is unavailable",
        )
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        try:
            decision = StageGateService().decide(
                session,
                continuation,
                gate_id.upper(),
                body,
                actor=actor,
                observed_workspace_fingerprint=observed_fingerprint,
            )
        except (StageGateError, ValueError) as error:
            return error_response(
                request,
                status_code=409,
                error_code=getattr(error, "code", "GATE_ID_INVALID"),
                message=getattr(error, "message", str(error)),
            )
        return {
            "decision_id": decision.id,
            "gate_id": decision.gate_id,
            "decision": decision.decision,
            "accepted": decision.accepted,
            "state_version": continuation.state_version,
            "idempotent_replay": replay,
        }


@router.post("/{run_id}/transformation/cancel")
def cancel_transformation(
    run_id: str,
    body: TransformationCancelRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        try:
            TransformationContinuationService().request_cancel(
                session,
                continuation.id,
                actor=actor,
                idempotency_key=body.idempotency_key,
                expected_state_version=body.expected_state_version,
            )
            active = session.scalar(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == run_id,
                    CommandExecutionModel.status.in_(("queued", "pending", "running")),
                )
            )
            if active is not None:
                CommandExecutorService().request_cancel(
                    session,
                    run_id,
                    active.id,
                    actor,
                    idempotency_key=f"{body.idempotency_key}:command",
                )
        except TransformationContinuationError as error:
            return error_response(
                request,
                status_code=409,
                error_code=error.code,
                message=error.message,
            )
        return _projection(session, continuation)


@router.post("/{run_id}/transformation/restart")
def restart_transformation(
    run_id: str,
    body: TransformationRestartRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        replay = session.scalar(
            select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == run_id,
                WorkflowEventModel.idempotency_key == body.idempotency_key,
                WorkflowEventModel.event_type == "TRANSFORMATION_CONTINUATION_RESUMED",
            )
        )
        if replay is not None:
            if (replay.payload or {}).get("expected_state_version") != body.expected_state_version:
                return error_response(
                    request,
                    status_code=409,
                    error_code="IDEMPOTENCY_PAYLOAD_MISMATCH",
                    message="Restart key was already used with a different payload",
                )
            return _projection(session, continuation)
        if continuation.state_version != body.expected_state_version:
            return error_response(
                request,
                status_code=409,
                error_code="TRANSFORMATION_STATE_CONFLICT",
                message="Transformer state changed; refresh authoritative state",
            )
        try:
            TransformationContinuationService().wake(session, continuation.id)
        except TransformationContinuationError as error:
            return error_response(
                request,
                status_code=409,
                error_code=error.code,
                message=error.message,
            )
        from app.domain.contracts import WorkflowEventType
        from app.state import StateTransitionService

        StateTransitionService(session).append_audit_event(
            run_id=run_id,
            idempotency_key=body.idempotency_key,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
            actor=actor,
            reason="operator restarted Transformer from durable state",
            occurred_at=continuation.updated_at,
            payload={
                "continuation_id": continuation.id,
                "expected_state_version": body.expected_state_version,
            },
        )
        return _projection(session, continuation)
