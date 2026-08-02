"""G12, immutable stage sealing, later-stage activation, and completion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, RunStatus, WorkflowEventType
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StagePromptRequestModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.services.command_registry_service import CommandRegistryService
from app.services.next_stage_materializer_service import (
    NextStageMaterializerError,
    NextStageMaterializerService,
)
from app.services.stage_sealing_service import StageSealingError, StageSealingService
from app.services.transformer_stage_service import TransformerStageError
from app.state import StateTransitionService, TransitionRequest


class TransformerSealingFlow:
    def __init__(
        self,
        *,
        scope,
        stage_service,
        gate_service,
        sealing_service=None,
        materializer=None,
    ) -> None:
        self._scope = scope
        self._stage = stage_service
        self._gates = gate_service
        self._sealing = sealing_service or StageSealingService()
        self._materializer = materializer or NextStageMaterializerService()

    def create_g12(self, continuation_id: str, worker_id: str) -> None:
        try:
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)
                context = self._sealing.context(session, continuation)
                plan = session.get(MigrationPlanModel, continuation.plan_id)
                if plan is None or plan.run_id != continuation.run_id:
                    raise StageSealingError("PLAN_BINDING_MISSING", "Migration plan for the run is missing")
                plan_version = plan.version
            cleanliness = self._sealing.verify_cleanliness(context)
        except StageSealingError as error:
            self._fail(continuation_id, worker_id, error)
            return
        root = Path(str(context["artifact_root"]))
        clean_artifact = LocalFilesystemArtifactStore(
            root.parent, fixed_run_root=root
        ).write_text_artifact(
            str(context["run_id"]),
            f"04_workflow_state/stages/{context['stage_id']}/seal/cleanliness.json",
            json.dumps(cleanliness, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=str(context["stage_id"]),
            created_by="stage-sealing-service",
            created_at=datetime.now(UTC),
            input_hashes={"g09": str(context["g09_package_checksum"])},
            policy_version="stage-cleanliness-v1",
        )
        payload = {
            **cleanliness,
            "gate_id": "G12",
            "plan_version": plan_version,
            "stage_plan_checksum": context["stage_plan_checksum"],
            "cleanliness_artifact_id": clean_artifact.ref.artifact_id,
            "cleanliness_checksum": clean_artifact.ref.checksum,
            "previous_chain_hash": context["previous_chain_hash"],
        }
        gate = self._stage.write_gate_package(
            run_id=str(context["run_id"]),
            stage_id=str(context["stage_id"]),
            artifact_root=str(context["artifact_root"]),
            gate_id="G12",
            payload=payload,
        )
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._stage.register_artifact(session, clean_artifact, continuation)
            self._stage.register_artifact(session, gate, continuation)
            self._gates.create(
                session,
                continuation,
                gate_id="G12",
                package_artifact_id=gate.ref.artifact_id,
                package_checksum=gate.ref.checksum,
                artifact_set_checksum=self._stage.checksum(
                    {
                        clean_artifact.ref.artifact_id: clean_artifact.ref.checksum,
                        gate.ref.artifact_id: gate.ref.checksum,
                    }
                ),
                workspace_fingerprint=str(cleanliness["workspace_fingerprint"]),
            )

    def seal(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            existing = session.scalar(
                select(StageCheckpointModel).where(
                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                    StageCheckpointModel.sealed.is_(True),
                )
            )
            if existing is not None:
                self._queue(continuation, "materialize_next_stage")
                return
            context = self._sealing.context(session, continuation)
            g12 = session.scalar(
                select(StageGatePackageModel)
                .where(
                    StageGatePackageModel.stage_id == continuation.current_stage_id,
                    StageGatePackageModel.gate_id == "G12",
                    StageGatePackageModel.status == "approved",
                )
                .order_by(StageGatePackageModel.gate_version.desc())
            )
            if g12 is None:
                self._block(continuation, "G12_APPROVAL_REQUIRED", "Approved G12 is missing")
                return
            g12_checksum = g12.package_checksum
        try:
            target, fingerprint, chain_hash, output, seal = self._sealing.seal(
                context, g12_checksum
            )
        except (StageSealingError, OSError, ValueError) as error:
            self._fail(continuation_id, worker_id, error)
            return
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            existing = session.scalar(
                select(StageCheckpointModel).where(
                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                    StageCheckpointModel.sealed.is_(True),
                )
            )
            if existing is None:
                for artifact in (output, seal):
                    self._stage.register_artifact(session, artifact, continuation)
                sequence = (
                    session.scalar(
                        select(func.max(StageCheckpointModel.sequence)).where(
                            StageCheckpointModel.stage_id == continuation.current_stage_id
                        )
                    )
                    or 0
                ) + 1
                session.add(
                    StageCheckpointModel(
                        id=f"seal-{continuation.current_stage_id}",
                        run_id=continuation.run_id,
                        stage_id=continuation.current_stage_id,
                        kind="sealed_output",
                        sequence=sequence,
                        workspace_alias="SEALED_STAGE_" + continuation.current_stage_id.upper(),
                        workspace_path=str(target),
                        workspace_fingerprint=fingerprint,
                        manifest_artifact_id=seal.ref.artifact_id,
                        manifest_checksum=chain_hash,
                        safe_for_resume=True,
                        sealed=True,
                        state_version=continuation.state_version,
                        created_at=datetime.now(UTC),
                    )
                )
                stage = session.get(MigrationStageModel, continuation.current_stage_id)
                stage.status = "sealed"
                stage.completed_at = datetime.now(UTC)
                StateTransitionService(session).append_audit_event(
                    run_id=continuation.run_id,
                    idempotency_key=f"{continuation.current_stage_id}:sealed",
                    event_type=WorkflowEventType.STAGE_SEALED,
                    actor="transformer",
                    reason="stage output sealed with chain-bound evidence",
                    occurred_at=datetime.now(UTC),
                    payload={
                        "stage_id": continuation.current_stage_id,
                        "chain_hash": chain_hash,
                        "workspace_fingerprint": fingerprint,
                    },
                )
            self._queue(continuation, "materialize_next_stage")

    def materialize(self, continuation_id: str, worker_id: str) -> None:
        try:
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)
                seal = session.scalar(
                    select(StageCheckpointModel).where(
                        StageCheckpointModel.stage_id == continuation.current_stage_id,
                        StageCheckpointModel.sealed.is_(True),
                    )
                )
                if seal is None:
                    raise NextStageMaterializerError(
                        "SEALED_STAGE_MISSING", "Current stage has no immutable seal"
                    )
                context = self._materializer.context(
                    session,
                    continuation,
                    seal.workspace_path,
                    seal.workspace_fingerprint,
                )
                run = session.get(MigrationRunModel, continuation.run_id)
                migration_plan = session.get(MigrationPlanModel, continuation.plan_id)
                artifact_root = run.artifact_root
            stage_plan = self._materializer.materialize(context)
        except NextStageMaterializerError as error:
            self._fail(continuation_id, worker_id, error)
            return
        if stage_plan is None:
            with self._scope() as session:
                self._queue(self._owned(session, continuation_id, worker_id), "complete_run")
            return
        root = Path(artifact_root)
        stored = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root).write_text_artifact(
            str(context["run_id"]),
            f"stages/{stage_plan.stage_id}/stage-execution-plan.json",
            json.dumps(stage_plan.model_dump(mode="json"), sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=stage_plan.stage_id,
            created_by="next-stage-materializer",
            created_at=datetime.now(UTC),
            input_hashes={"sealed_output": str(context["sealed_fingerprint"])},
            policy_version="next-stage-materializer-v1",
        )
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            existing = session.get(StageExecutionPlanModel, stage_plan.stage_plan_id)
            if existing is not None and existing.checksum != stage_plan.checksum:
                self._block(
                    continuation,
                    "NEXT_STAGE_IDEMPOTENCY_CONFLICT",
                    "Materialized stage ID is bound to different content",
                )
                return
            registry = CommandRegistryService()
            registry.seed_defaults(session)
            for references in stage_plan.commands.values():
                for reference in references:
                    if (
                        registry.find_registered_template(
                            session,
                            template_id=reference.template_id,
                            command_id=reference.command_id,
                            version=reference.template_version,
                        )
                        is None
                    ):
                        self._block(
                            continuation,
                            "COMMAND_CATALOGUE_DRIFT",
                            "Materialized command template is not registered",
                        )
                        return
            if existing is None:
                stage = MigrationStageModel(
                    id=stage_plan.stage_id,
                    run_id=continuation.run_id,
                    stage_order=session.query(MigrationStageModel)
                    .filter_by(run_id=continuation.run_id)
                    .count()
                    + 1,
                    source_version_family=stage_plan.source_family,
                    target_version_family=stage_plan.target_family,
                    source_version_detected=stage_plan.source_exact,
                    target_version_resolved=stage_plan.target_exact,
                    source_angular_version=stage_plan.source_exact,
                    target_angular_version=stage_plan.target_exact,
                    status="planned",
                    created_at=datetime.now(UTC),
                )
                existing = StageExecutionPlanModel(
                    id=stage_plan.stage_plan_id,
                    run_id=continuation.run_id,
                    migration_plan_id=migration_plan.id,
                    stage_id=stage_plan.stage_id,
                    idempotency_key=f"materialize:{stage_plan.stage_id}",
                    request_checksum=stage_plan.input_fingerprint,
                    actor="transformer",
                    status="approved",
                    version=stage_plan.plan_version,
                    stage_plan=stage_plan.model_dump(mode="json"),
                    checksum=stage_plan.checksum,
                    artifact_ids=[stored.ref.artifact_id],
                    artifact_checksums={stored.ref.artifact_id: stored.ref.checksum},
                    state_version=continuation.state_version,
                    event_sequence=0,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add_all([stage, existing])
                session.add(
                    ArtifactMetadataModel(
                        id="metadata-" + stored.ref.artifact_id,
                        run_id=continuation.run_id,
                        stage_id=stage_plan.stage_id,
                        artifact_type=stored.ref.artifact_type.value,
                        relative_path=stored.ref.relative_path,
                        checksum=stored.ref.checksum,
                        created_at=stored.ref.created_at,
                        finalized_at=stored.ref.created_at,
                        immutable=True,
                    )
                )
                session.add(
                    ActivePlanVersionModel(
                        id=f"active-stage-{stage_plan.stage_id}",
                        run_id=continuation.run_id,
                        scope=stage_plan.stage_id,
                        migration_plan_id=migration_plan.id,
                        stage_plan_id=existing.id,
                        version=existing.version,
                        state_version=continuation.state_version,
                        updated_at=datetime.now(UTC),
                    )
                )
                StateTransitionService(session).append_audit_event(
                    run_id=continuation.run_id,
                    idempotency_key=f"{stage_plan.stage_id}:materialized",
                    event_type=WorkflowEventType.STAGE_PLAN_CREATED,
                    actor="transformer",
                    reason="next exact stage derived from sealed approved route",
                    occurred_at=datetime.now(UTC),
                    payload={
                        "stage_id": stage_plan.stage_id,
                        "stage_plan_id": existing.id,
                        "source_fingerprint": str(context["sealed_fingerprint"]),
                    },
                )
            prior_binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == continuation.run_id,
                    StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if prior_binding:
                prior_binding.active = False
            run = session.get(MigrationRunModel, continuation.run_id)
            aliases = dict(run.workspace_aliases or {})
            aliases["BASELINE_SANDBOX"] = str(context["sealed_path"])
            run.workspace_aliases = aliases
            continuation.current_stage_id = stage_plan.stage_id
            continuation.stage_plan_id = existing.id
            continuation.stage_plan_checksum = existing.checksum
            continuation.status = "queued"
            continuation.current_node = "prepare_workspace"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.last_error_code = None
            continuation.last_error_message = None
            continuation.state_version += 1
            continuation.updated_at = datetime.now(UTC)

    def complete(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            route = list((plan.plan or {}).get("route") or [])
            stages = {
                item.id: item
                for item in session.query(MigrationStageModel)
                .filter_by(run_id=continuation.run_id)
                .all()
            }
            if not route or any(stage_id not in stages or stages[stage_id].status != "sealed" for stage_id in route):
                self._block(
                    continuation,
                    "COMPLETION_INVARIANT_FAILED",
                    "Every approved route stage must have an immutable seal",
                )
                return
            for stage_id in route:
                approved = {
                    item.gate_id
                    for item in session.query(StageGatePackageModel).filter(
                        StageGatePackageModel.stage_id == stage_id,
                        StageGatePackageModel.status == "approved",
                    )
                }
                if not {"G07", "G08", "G09", "G12"}.issubset(approved):
                    self._block(
                        continuation,
                        "COMPLETION_GATE_INVARIANT_FAILED",
                        f"Stage {stage_id} lacks required approved gates",
                    )
                    return
            if session.scalar(
                select(CommandExecutionModel.id).where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.status.in_(("queued", "pending", "running")),
                )
            ) or session.scalar(
                select(StagePromptRequestModel.id).where(
                    StagePromptRequestModel.run_id == continuation.run_id,
                    StagePromptRequestModel.status.not_in(("decided", "cancelled", "stale")),
                )
            ) or session.scalar(
                select(RepairAttemptModel.id).where(
                    RepairAttemptModel.run_id == continuation.run_id,
                    RepairAttemptModel.status.in_(
                        (
                            "evidence_frozen",
                            "proposed",
                            "review_accepted",
                            "waiting_g10",
                            "applying",
                            "applied",
                            "revalidating",
                            "revalidating_affected",
                        )
                    ),
                )
            ):
                self._block(
                    continuation,
                    "COMPLETION_WORK_REMAINS",
                    "Active command, prompt, or repair work remains",
                )
                return
            run = session.get(MigrationRunModel, continuation.run_id)
            StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run.id,
                    expected_state_version=run.state_version,
                    idempotency_key=f"{continuation.id}:completed",
                    event_type=WorkflowEventType.STAGED_MIGRATION_COMPLETED,
                    next_run_status=RunStatus.COMPLETED,
                    actor="transformer",
                    reason="all approved route stages are sealed and evidence-complete",
                    occurred_at=datetime.now(UTC),
                    payload={
                        "stage_id": continuation.current_stage_id,
                        "sealed_stage_count": len(route),
                    },
                )
            )
            continuation.status = "completed"
            continuation.current_node = "terminal"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.completed_at = datetime.now(UTC)
            continuation.state_version += 1
            continuation.updated_at = datetime.now(UTC)

    def _fail(self, continuation_id, worker_id, error) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._block(
                continuation,
                getattr(error, "code", "STAGE_SEALING_FAILED"),
                getattr(error, "message", str(error)),
            )

    @staticmethod
    def _owned(session, continuation_id: str, worker_id: str):
        continuation = session.get(TransformationContinuationModel, continuation_id)
        if (
            continuation is None
            or continuation.status != "running"
            or continuation.worker_id != worker_id
        ):
            raise TransformerStageError(
                "TRANSFORMATION_CLAIM_STALE", "Worker no longer owns continuation"
            )
        return continuation

    @staticmethod
    def _queue(continuation, node: str) -> None:
        continuation.status = "queued"
        continuation.current_node = node
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)

    @staticmethod
    def _block(continuation, code: str, message: str) -> None:
        continuation.status = "blocked"
        continuation.last_error_code = code
        continuation.last_error_message = message
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)
