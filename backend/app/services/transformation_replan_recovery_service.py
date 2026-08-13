"""Governed recovery from an immutable failed transformation into a new G06."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

from sqlalchemy import select

from app.api.planning_review_contracts import PlanningExplanationApiRequest
from app.api.transformation_replan_contracts import (
    TransformationReplanRecoveryRequest,
    TransformationReplanRecoveryResponse,
)
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, RunStatus, WorkflowEventType
from app.domain.planning import PlanArtifactInput, PlanGenerationRequest
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    BuildSystemDecisionModel,
    CommandExecutionModel,
    CompatibilityResolutionModel,
    G05ApprovalModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    PlanApprovalStaleModel,
    PlanRevisionModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StageReconstructionRecordModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.planning_application_service import PlanningApplicationService
from app.services.planning_review_evidence_application_service import (
    PlanningReviewEvidenceApplicationService,
)
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import TransformerStageService
from app.state import StateTransitionService
from app.state.transition_service import TransitionRequest


class TransformationReplanRecoveryError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class TransformationReplanRecoveryService:
    """Reconstruct one blocked stage and deterministically replace its active plan."""

    _KARMA_FAILURE_TOKENS = (
        "ERESOLVE could not resolve",
        "@angular-devkit/build-angular@12.2.18",
        'karma@"~5.1.0"',
        'karma@"^6.3.0"',
        "karma@6.4.4",
    )
    _MIGRATION_VERSION_FAILURE_TOKENS = (
        "Invalid Version: 9-beta",
        "run_installed_migrations.cjs",
        "node_modules\\semver\\",
    )
    _ANGULAR_ESLINT_18_FAILURE_TOKENS = (
        "Cannot read properties of undefined (reading 'startsWith')",
        "@angular-eslint\\schematics\\dist\\migrations\\update-18-2-0",
        "update-18-2-0.js",
    )
    _ANGULAR_ESLINT_18_DISPOSITIONS = (
        "devDependencies[@typescript-eslint/eslint-plugin]=^7.2.0",
        "devDependencies[@typescript-eslint/parser]=^7.2.0",
        "devDependencies[eslint]=^8.57.0",
    )

    def __init__(self, *, scope=session_scope, now_provider=None) -> None:
        self._scope = scope
        self._now = now_provider or (lambda: datetime.now(UTC))

    def recover(
        self,
        run_id: str,
        payload: TransformationReplanRecoveryRequest,
        actor: str,
    ) -> TransformationReplanRecoveryResponse:
        replay = self._replay(run_id, payload, actor)
        if replay is not None:
            return replay
        context = self._reserve(run_id, payload, actor)
        request = self._generation_request(context, payload, actor)
        generated = PlanningApplicationService().generate(
            request,
            plan_version=context["old_plan"].version + 1,
        )
        stage = generated.first_stage_plan
        if stage is None or not self._proven_disposition_planned(
            context["failure_profile"], stage
        ):
            raise TransformationReplanRecoveryError(
                "PROVEN_DISPOSITION_NOT_PLANNED",
                "The regenerated plan does not contain the proven failure disposition.",
            )
        restored = self._reconstruct(context)
        artifacts = self._write_artifacts(context, payload, actor, generated, restored)
        state_version = self._persist(
            run_id,
            payload,
            actor,
            context,
            generated,
            restored,
            artifacts,
        )
        prerequisites = [
            PlanArtifactInput(artifact_id=item, checksum=context["g05"].prerequisite_artifact_checksums[item])
            for item in context["g05"].prerequisite_artifact_ids
        ]
        review = PlanningReviewEvidenceApplicationService(scope=self._scope).explain(
            run_id,
            PlanningExplanationApiRequest(
                expected_state_version=state_version,
                idempotency_key=f"{payload.idempotency_key}:g06",
                plan=generated.plan.model_dump(mode="json"),
                stage_plan=stage.model_dump(mode="json"),
                artifact_set_checksum=context["g05"].artifact_set_checksum,
                prerequisite_artifacts=prerequisites,
                workspace_fingerprint=restored,
                plan_version=generated.plan.version,
                correlation_id=payload.correlation_id,
            ),
            actor,
        )
        if review.gate_status != "pending" or not review.package_checksum:
            raise TransformationReplanRecoveryError(
                "REGENERATED_G06_UNAVAILABLE",
                "The regenerated plan did not produce a pending G06 package.",
                503,
            )
        return self._response(run_id, payload, replay=False)

    def _reserve(self, run_id, payload, actor):
        now = self._now()
        with self._scope() as session:
            context = self._validated_context(session, run_id, payload, actor)
            existing = session.scalar(select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == run_id,
                WorkflowEventModel.idempotency_key == f"{payload.idempotency_key}:started",
            ))
            if existing is not None:
                if (existing.payload or {}).get("request_checksum") != self._request_checksum(run_id, payload, actor):
                    raise TransformationReplanRecoveryError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "The recovery idempotency key was already used with a different payload.",
                    )
                return context
            StateTransitionService(session).append_audit_event(
                run_id=run_id,
                idempotency_key=f"{payload.idempotency_key}:started",
                event_type=WorkflowEventType.TRANSFORMATION_REPLAN_RECOVERY_STARTED,
                actor=actor,
                reason="governed replan recovery reserved",
                occurred_at=now,
                payload={
                    "request_checksum": self._request_checksum(run_id, payload, actor),
                    "continuation_id": context["continuation"].id,
                    "failed_execution_id": payload.failed_execution_id,
                    "checkpoint_id": context["checkpoint"].id,
                },
            )
            return context

    @staticmethod
    def _reconstruct(context) -> str:
        """Materialize the baseline inside the registered stage root before swapping."""
        stage_root = Path(context["stage_root"])
        temporary = stage_root / (
            f".{context['continuation'].current_stage_id}.replan-source-{uuid4().hex[:12]}"
        )
        try:
            report = StageSandboxCopier().copy(
                Path(context["baseline_path"]), temporary, registered_root=stage_root
            )
            if report.fingerprint != context["checkpoint"].workspace_fingerprint:
                raise TransformationReplanRecoveryError(
                    "SAFE_PRE_TRANSFORMATION_CHECKPOINT_UNAVAILABLE",
                    "The materialized recovery source does not match the safe checkpoint.",
                )
            return TransformerStageService().reconstruct_workspace(
                str(temporary), context["workspace_path"], str(stage_root),
                context["checkpoint"].workspace_fingerprint,
            )
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def _validated_context(self, session, run_id, payload, actor):
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise TransformationReplanRecoveryError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.actor and run.actor != actor:
            raise TransformationReplanRecoveryError("RUN_NOT_AUTHORIZED", "Migration run is not owned by this actor.", 403)
        if run.state_version != payload.expected_state_version:
            raise TransformationReplanRecoveryError("STALE_STATE_VERSION", "The run state version changed.")
        continuation = session.scalar(
            select(TransformationContinuationModel).where(TransformationContinuationModel.run_id == run_id)
        )
        if (
            continuation is None
            or continuation.state_version != payload.expected_continuation_state_version
            or continuation.status != "blocked"
            or continuation.current_node != "classify_failure"
            or continuation.last_error_code
            not in {"CHECKPOINT_RECOVERY_FAILED", "CHECKPOINT_INTEGRITY_FAILED"}
        ):
            raise TransformationReplanRecoveryError(
                "REPLAN_RECOVERY_NOT_ELIGIBLE",
                "The continuation is not at the exact governed checkpoint-recovery blocker.",
            )
        old_plan = session.get(MigrationPlanModel, continuation.plan_id)
        old_stage = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        if (
            old_plan is None
            or old_stage is None
            or old_plan.checksum != payload.approved_plan_checksum
            or old_stage.checksum != payload.approved_stage_plan_checksum
            or old_plan.status != "approved_for_execution"
            or old_stage.status not in {"approved", "approved_for_execution"}
        ):
            raise TransformationReplanRecoveryError(
                "APPROVED_PLAN_BINDING_STALE",
                "The blocked continuation is not bound to the expected approved plan.",
            )
        failed = session.get(CommandExecutionModel, payload.failed_execution_id)
        result_meta = session.get(ArtifactMetadataModel, f"metadata-{failed.result_artifact_id}") if failed else None
        failure = failed.failure_message or "" if failed else ""
        failure_profile = self._failure_profile(failed, failure)
        blocker_matches_failure = (
            continuation.last_error_code == "CHECKPOINT_RECOVERY_FAILED"
            or (
                continuation.last_error_code == "CHECKPOINT_INTEGRITY_FAILED"
                and failure_profile == "angular-eslint-18-parser-guard"
            )
        )
        if (
            failed is None
            or failed.run_id != run_id
            or failed.stage_id != continuation.current_stage_id
            or failed.status != "failed"
            or failed.exit_code != 1
            or failed.checkpoint_id is None
            or result_meta is None
            or not result_meta.immutable
            or result_meta.checksum != payload.failed_result_checksum
            or failure_profile is None
            or not blocker_matches_failure
        ):
            raise TransformationReplanRecoveryError(
                "FAILED_EXECUTION_EVIDENCE_MISMATCH",
                "The supplied failure is not an immutable supported transformation recovery case.",
            )
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        checkpoint = session.get(StageCheckpointModel, binding.source_checkpoint_id) if binding else None
        aliases = dict(run.workspace_aliases or {})
        baseline = Path(aliases.get("BASELINE_SANDBOX", ""))
        stage_root = Path(aliases.get("STAGE_SANDBOX", ""))
        if (
            binding is None
            or checkpoint is None
            or checkpoint.kind != "pre_bootstrap"
            or not checkpoint.safe_for_resume
            or checkpoint.run_id != run_id
            or checkpoint.stage_id != continuation.current_stage_id
            or not baseline.is_dir()
            or not stage_root.is_dir()
            or StageSandboxCopier.fingerprint(baseline) != checkpoint.workspace_fingerprint
        ):
            raise TransformationReplanRecoveryError(
                "SAFE_PRE_TRANSFORMATION_CHECKPOINT_UNAVAILABLE",
                "The last safe pre-transformation checkpoint cannot be reconstructed exactly.",
            )
        g05 = session.scalar(
            select(G05ApprovalModel)
            .where(G05ApprovalModel.run_id == run_id, G05ApprovalModel.status == "approved")
            .order_by(G05ApprovalModel.created_at.desc())
        )
        resolution = session.scalar(
            select(CompatibilityResolutionModel)
            .where(CompatibilityResolutionModel.run_id == run_id)
            .order_by(CompatibilityResolutionModel.created_at.desc())
        )
        if g05 is None or resolution is None or resolution.package_checksum != g05.package_checksum:
            raise TransformationReplanRecoveryError(
                "APPROVED_FEASIBILITY_BINDING_STALE",
                "The approved feasibility evidence required for deterministic regeneration is stale.",
            )
        return {
            "run": run,
            "continuation": continuation,
            "old_plan": old_plan,
            "old_stage": old_stage,
            "failed": failed,
            "binding": binding,
            "checkpoint": checkpoint,
            "g05": g05,
            "resolution": resolution,
            "baseline_path": str(baseline.resolve(strict=True)),
            "stage_root": str(stage_root.resolve(strict=True)),
            "workspace_path": binding.workspace_path,
            "artifact_root": run.artifact_root,
            "failure_profile": failure_profile,
        }

    @classmethod
    def _failure_profile(cls, failed, failure: str) -> str | None:
        if failed is None:
            return None
        if (
            failed.command_id == "npm-lockfile-generate"
            and all(token in failure for token in cls._KARMA_FAILURE_TOKENS)
        ):
            return "karma-5-to-6-disposition"
        arguments = list(failed.arguments or [])
        if (
            failed.command_id == "angular-migrate-only"
            and len(arguments) == 4
            and str(arguments[0]).endswith("run_installed_migrations.cjs")
            and arguments[1:] == ["@angular/core", "11.0.0", "12.2.17"]
            and all(
                token in failure
                for token in cls._MIGRATION_VERSION_FAILURE_TOKENS
            )
        ):
            return "angular-core-historical-migration-version"
        if (
            failed.command_id == "angular-migrate-only"
            and len(arguments) == 4
            and str(arguments[0]).endswith("run_installed_migrations.cjs")
            and arguments[1:] == [
                "@angular-eslint/schematics",
                "17.0.0",
                "18.4.3",
            ]
            and all(token in failure for token in cls._ANGULAR_ESLINT_18_FAILURE_TOKENS)
        ):
            return "angular-eslint-18-parser-guard"
        return None

    @classmethod
    def _proven_disposition_planned(cls, failure_profile, stage) -> bool:
        commands = stage.commands["angular_update"]
        if failure_profile == "karma-5-to-6-disposition":
            required = ("devDependencies[karma]=6.4.4",)
        elif failure_profile == "angular-eslint-18-parser-guard":
            required = cls._ANGULAR_ESLINT_18_DISPOSITIONS
        elif failure_profile == "angular-core-historical-migration-version":
            return any(
                ref.command_id == "angular-migrate-only"
                and ref.parameter_bindings.get("package") == "@angular/core"
                for ref in commands
            )
        else:
            return False
        return all(
            any(ref.command_id == "npm-pkg-set" and value in ref.arguments for ref in commands)
            for value in required
        )

    @staticmethod
    def _generation_request(context, payload, actor):
        old_stage = context["old_stage"].stage_plan
        package = context["resolution"].package
        route = package.get("route") or []
        try:
            current_index = next(
                index
                for index, item in enumerate(route)
                if item["source_family"] == old_stage["source_family"]
                and item["target_family"] == old_stage["target_family"]
            )
        except StopIteration as error:
            raise TransformationReplanRecoveryError(
                "CURRENT_STAGE_ROUTE_UNAVAILABLE",
                "The blocked stage is not present in the approved compatibility route.",
            ) from error
        remaining_route = route[current_index:]
        runtime_checksum = next(
            ref.get("runtime_profile_checksum")
            for refs in (old_stage.get("commands") or {}).values()
            for ref in refs
            if ref.get("runtime_profile_checksum")
        )
        prerequisites = tuple(
            PlanArtifactInput(artifact_id=item, checksum=context["g05"].prerequisite_artifact_checksums[item])
            for item in context["g05"].prerequisite_artifact_ids
        )
        return PlanGenerationRequest(
            run_id=context["run"].id,
            expected_state_version=payload.expected_state_version,
            idempotency_key=f"{payload.idempotency_key}:plan",
            actor=actor,
            correlation_id=payload.correlation_id,
            source_exact=old_stage["source_exact"],
            source_family=old_stage["source_family"],
            target_family=context["old_plan"].plan["target_family"],
            catalogue_version=context["old_plan"].plan["catalogue_version"],
            input_fingerprint=context["checkpoint"].workspace_fingerprint,
            evidence_set_checksum=context["g05"].artifact_set_checksum,
            input_workspace_fingerprint=context["checkpoint"].workspace_fingerprint,
            execution_profile_id=old_stage["execution_profile_id"],
            execution_profile_checksum=runtime_checksum,
            package_manager=old_stage["package_manager"],
            resolved_scripts=old_stage["resolved_scripts"],
            project_targets=old_stage["project_targets"],
            stage_route=tuple(
                (
                    item["source_family"], item["target_family"], item["stage_id"],
                    item["target_angular_exact"], item.get("target_cli_exact", item["target_angular_exact"]),
                )
                for item in remaining_route
            ),
            target_cli_exact=remaining_route[0].get("target_cli_exact"),
            builder=old_stage["build_system_decision"]["builder"],
            prerequisite_artifacts=prerequisites,
            validation_policy_id=old_stage["validation_policy"]["policy_id"],
            recovery_policy_id=old_stage["recovery_policy"]["policy_id"],
            repair_policy_id=old_stage["repair_policy"]["policy_id"],
        )

    def _write_artifacts(self, context, payload, actor, generated, restored):
        now = self._now()
        plan = generated.plan
        stage = generated.first_stage_plan
        store = LocalFilesystemArtifactStore(Path(context["artifact_root"]), fixed_run_root=Path(context["artifact_root"]))
        report = {
            "run_id": context["run"].id,
            "continuation_id": context["continuation"].id,
            "failed_execution_id": payload.failed_execution_id,
            "failed_result_checksum": payload.failed_result_checksum,
            "reconstruction_checkpoint_id": context["checkpoint"].id,
            "reconstruction_fingerprint": restored,
            "previous_plan_checksum": context["old_plan"].checksum,
            "previous_stage_plan_checksum": context["old_stage"].checksum,
            "regenerated_plan_checksum": plan.checksum,
            "regenerated_stage_plan_checksum": stage.checksum,
            "proven_disposition": self._disposition_summary(context["failure_profile"]),
            "recovery_reason": context["failure_profile"],
            "actor": actor,
            "request_checksum": self._request_checksum(context["run"].id, payload, actor),
        }
        values = {
            f"03_planning/versions/v{plan.version}/migration-plan.json": plan.model_dump(mode="json"),
            f"stages/{stage.stage_id}/versions/v{plan.version}/stage-execution-plan.json": stage.model_dump(mode="json"),
            f"03_planning/versions/v{plan.version}/replan-recovery.json": report,
        }
        stored = []
        for relative_path, value in values.items():
            stored.append(store.write_text_artifact(
                context["run"].id,
                relative_path,
                json.dumps(value, sort_keys=True, indent=2),
                ArtifactType.JSON,
                stage_id=stage.stage_id if relative_path.startswith("stages/") else None,
                created_by="transformation-replan-recovery",
                created_at=now,
                input_hashes={"failed_result": payload.failed_result_checksum, "checkpoint": restored},
                policy_version="transformation-replan-recovery-v1",
            ))
        return stored

    def _persist(self, run_id, payload, actor, context, generated, restored, artifacts):
        now = self._now()
        with self._scope() as session:
            current = self._validated_context(session, run_id, payload, actor)
            live = StageSandboxCopier.fingerprint(Path(current["workspace_path"]))
            if live != restored or restored != current["checkpoint"].workspace_fingerprint:
                raise TransformationReplanRecoveryError(
                    "RECONSTRUCTED_WORKSPACE_FINGERPRINT_MISMATCH",
                    "The reconstructed workspace no longer matches the safe checkpoint.",
                )
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id,
                expected_state_version=payload.expected_state_version,
                idempotency_key=f"{payload.idempotency_key}:completed",
                event_type=WorkflowEventType.TRANSFORMATION_REPLAN_RECOVERY_COMPLETED,
                actor=actor,
                reason="governed transformation recovery regenerated the detailed plan",
                occurred_at=now,
                payload={
                    "failed_execution_id": payload.failed_execution_id,
                    "checkpoint_id": current["checkpoint"].id,
                    "previous_plan_checksum": current["old_plan"].checksum,
                    "regenerated_plan_checksum": generated.plan.checksum,
                    "regenerated_stage_plan_checksum": generated.first_stage_plan.checksum,
                },
                next_run_status=RunStatus.WAITING_PLAN_APPROVAL,
                next_run_phase="FEASIBILITY_PLANNING",
                next_phase_status="waiting_approval",
                next_approval_status="pending",
            ))
            artifact_ids = [item.ref.artifact_id for item in artifacts]
            artifact_checksums = {item.ref.artifact_id: item.ref.checksum for item in artifacts}
            for item in artifacts:
                session.add(ArtifactMetadataModel(
                    id=f"metadata-{item.ref.artifact_id}", run_id=run_id,
                    stage_id=item.ref.stage_id, artifact_type=item.ref.artifact_type.value,
                    relative_path=item.ref.relative_path, checksum=item.ref.checksum,
                    created_at=item.ref.created_at, finalized_at=item.ref.created_at,
                    immutable=True, correlation_id=payload.correlation_id,
                ))
            plan = generated.plan
            stage = generated.first_stage_plan
            plan_row = MigrationPlanModel(
                id=plan.plan_id, run_id=run_id, idempotency_key=f"{payload.idempotency_key}:plan",
                request_checksum=self._request_checksum(run_id, payload, actor), actor=actor,
                correlation_id=payload.correlation_id, status="regenerated", version=plan.version,
                plan=plan.model_dump(mode="json"), checksum=plan.checksum,
                artifact_ids=artifact_ids, artifact_checksums=artifact_checksums,
                state_version=transition.next_state_version, event_sequence=transition.event_sequence,
                created_at=now, updated_at=now,
            )
            stage_row = StageExecutionPlanModel(
                id=stage.stage_plan_id, run_id=run_id, migration_plan_id=plan.plan_id,
                stage_id=stage.stage_id, idempotency_key=f"{payload.idempotency_key}:plan",
                request_checksum=plan_row.request_checksum, actor=actor,
                correlation_id=payload.correlation_id, status="regenerated", version=plan.version,
                stage_plan=stage.model_dump(mode="json"), checksum=stage.checksum,
                artifact_ids=artifact_ids, artifact_checksums=artifact_checksums,
                state_version=transition.next_state_version, event_sequence=transition.event_sequence,
                created_at=now, updated_at=now,
            )
            session.add_all([plan_row, stage_row])
            session.flush()
            session.add(BuildSystemDecisionModel(
                id=f"decision-{uuid4().hex[:12]}", run_id=run_id,
                stage_plan_id=stage_row.id, decision_id=stage.build_system_decision.decision_id,
                decision=stage.build_system_decision.model_dump(mode="json"),
                checksum=stage.build_system_decision.checksum, created_at=now,
            ))
            pointers = session.scalars(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id)).all()
            for pointer in pointers:
                pointer.migration_plan_id = plan_row.id
                pointer.stage_plan_id = stage_row.id if pointer.scope != "migration" else None
                pointer.version = plan.version
                pointer.state_version = transition.next_state_version
                pointer.updated_at = now
            stale_ids = []
            old_g06 = session.get(G06ApprovalModel, current["continuation"].g06_approval_id)
            if old_g06 is not None:
                old_g06.status = "stale"
                old_g06.stale_reason = "governed transformation replan recovery"
                old_g06.updated_at = now
                stale_ids.append(("G06", old_g06.id))
            for gate in session.scalars(select(StageGatePackageModel).where(
                StageGatePackageModel.run_id == run_id,
                StageGatePackageModel.stage_id == current["continuation"].current_stage_id,
                StageGatePackageModel.status.in_(("pending", "approved")),
            )).all():
                gate.status = "stale"
                gate.stale_at = now
                stale_ids.append((gate.gate_id, gate.id))
            for gate_id, approval_id in stale_ids:
                session.add(PlanApprovalStaleModel(
                    id=f"stale-{uuid4().hex[:12]}", run_id=run_id, gate_id=gate_id,
                    approval_id=approval_id, previous_plan_version=current["old_plan"].version,
                    new_plan_version=plan.version, reason="governed transformation replan recovery",
                    state_version=transition.next_state_version, event_sequence=transition.event_sequence,
                    created_at=now,
                ))
                StateTransitionService(session).append_audit_event(
                    run_id=run_id, idempotency_key=f"{payload.idempotency_key}:stale:{approval_id}",
                    event_type=WorkflowEventType.APPROVAL_MARKED_STALE, actor=actor,
                    reason="downstream approval marked stale by regenerated plan", occurred_at=now,
                    payload={"approval_id": approval_id, "new_plan_version": plan.version},
                )
            continuation = current["continuation"]
            continuation.status = "waiting_gate"
            continuation.current_node = "validate_g06"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.next_attempt_at = None
            continuation.waiting_execution_id = None
            continuation.last_error_code = "REPLAN_G06_REQUIRED"
            continuation.last_error_message = "A regenerated checksum-bound G06 requires explicit human approval"
            continuation.state_version += 1
            continuation.updated_at = now
            binding = current["binding"]
            binding.workspace_fingerprint = restored
            binding.last_verified_fingerprint = restored
            binding.last_verified_at = now
            session.add(StageReconstructionRecordModel(
                id=f"reconstruction-{uuid4().hex[:12]}", run_id=run_id,
                stage_id=continuation.current_stage_id, checkpoint_id=current["checkpoint"].id,
                reason="transformation_replan_recovery",
                source_workspace_fingerprint=current["checkpoint"].workspace_fingerprint,
                restored_workspace_fingerprint=restored,
                created_from_execution_id=payload.failed_execution_id, attempt_id=None,
                state_version=continuation.state_version, created_at=now,
            ))
            diff = {
                "from_version": current["old_plan"].version, "to_version": plan.version,
                "changed_fields": self._changed_fields(current["failure_profile"]),
                "proven_disposition": self._disposition_summary(current["failure_profile"]),
                "recovery_reason": current["failure_profile"],
                "failed_execution_id": payload.failed_execution_id,
            }
            session.add(PlanRevisionModel(
                id=f"plan-revision-{uuid4().hex[:12]}", run_id=run_id,
                idempotency_key=payload.idempotency_key,
                request_checksum=self._request_checksum(run_id, payload, actor), actor=actor,
                correlation_id=payload.correlation_id, previous_plan_id=current["old_plan"].id,
                migration_plan_id=plan_row.id, stage_plan_id=stage_row.id, version=plan.version,
                status="recovered_and_regenerated", diff=diff,
                diff_checksum=self._checksum(diff), stale_approval_ids=[item[1] for item in stale_ids],
                artifact_ids=artifact_ids, artifact_checksums=artifact_checksums,
                state_version=transition.next_state_version, event_sequence=transition.event_sequence,
                created_at=now, updated_at=now,
            ))
            return transition.next_state_version

    @classmethod
    def _changed_fields(cls, failure_profile):
        if failure_profile in {
            "karma-5-to-6-disposition",
            "angular-eslint-18-parser-guard",
        }:
            return ["stage_plan.commands.angular_update"]
        return ["plan.version", "command_runtime.legacy_migration_version_normalization"]

    @classmethod
    def _disposition_summary(cls, failure_profile):
        if failure_profile == "karma-5-to-6-disposition":
            return "devDependencies[karma]=6.4.4"
        if failure_profile == "angular-eslint-18-parser-guard":
            return list(cls._ANGULAR_ESLINT_18_DISPOSITIONS)
        return "normalize historical installed-migration version markers"

    def _replay(self, run_id, payload, actor):
        with self._scope() as session:
            revision = session.scalar(select(PlanRevisionModel).where(
                PlanRevisionModel.run_id == run_id,
                PlanRevisionModel.idempotency_key == payload.idempotency_key,
            ))
            if revision is None:
                return None
            if revision.request_checksum != self._request_checksum(run_id, payload, actor):
                raise TransformationReplanRecoveryError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "The recovery idempotency key was already used with a different payload.",
                )
        return self._response(run_id, payload, replay=True)

    def _response(self, run_id, payload, *, replay):
        with self._scope() as session:
            revision = session.scalar(select(PlanRevisionModel).where(
                PlanRevisionModel.run_id == run_id,
                PlanRevisionModel.idempotency_key == payload.idempotency_key,
            ))
            plan = session.get(MigrationPlanModel, revision.migration_plan_id)
            stage = session.get(StageExecutionPlanModel, revision.stage_plan_id)
            continuation = session.scalar(select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            ))
            reconstruction = session.scalar(select(StageReconstructionRecordModel).where(
                StageReconstructionRecordModel.run_id == run_id,
                StageReconstructionRecordModel.created_from_execution_id == payload.failed_execution_id,
                StageReconstructionRecordModel.reason == "transformation_replan_recovery",
            ).order_by(StageReconstructionRecordModel.created_at.desc()))
            gate = session.scalar(select(G06ApprovalModel).where(
                G06ApprovalModel.run_id == run_id,
                G06ApprovalModel.plan_version == plan.version,
                G06ApprovalModel.status == "pending",
            ).order_by(G06ApprovalModel.created_at.desc()))
            run = session.get(MigrationRunModel, run_id)
            if not all((revision, plan, stage, continuation, reconstruction, gate, run)):
                raise TransformationReplanRecoveryError(
                    "REGENERATED_G06_UNAVAILABLE", "The recovery completed without a complete pending G06 package.", 503
                )
            return TransformationReplanRecoveryResponse(
                run_id=run_id, continuation_id=continuation.id,
                failed_execution_id=payload.failed_execution_id,
                reconstruction_checkpoint_id=reconstruction.checkpoint_id,
                restored_workspace_fingerprint=reconstruction.restored_workspace_fingerprint,
                previous_plan_checksum=payload.approved_plan_checksum,
                previous_stage_plan_checksum=payload.approved_stage_plan_checksum,
                plan=plan.plan, stage_plan=stage.stage_plan,
                plan_checksum=plan.checksum, stage_plan_checksum=stage.checksum,
                g06_id=gate.id, g06_status=gate.status,
                g06_package_checksum=gate.package_checksum,
                g06_artifact_set_checksum=gate.artifact_set_checksum,
                state_version=run.state_version, idempotent_replay=replay,
            )

    @staticmethod
    def _request_checksum(run_id, payload, actor):
        return TransformationReplanRecoveryService._checksum({
            "run_id": run_id, "actor": actor, **payload.model_dump(mode="json")
        })

    @staticmethod
    def _checksum(value):
        return "sha256:" + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
