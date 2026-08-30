"""Authoritative protected stage-start transition and preparation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, CommandPolicyValidateRequestDto, RunStatus, WorkflowEventType
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    WorkspaceGenerationModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.planning_review_application_service import PlanRevisionService, PlanningReviewApplicationError
from app.services.command_executor_service import CommandExecutorError, CommandExecutorService
from app.services.command_registry_service import (
    CommandPolicyEngineService,
    CommandPolicyError,
    CommandRegistryService,
)
from app.services.stage_preparation_application_service import (
    StagePreparationApplicationService,
    StagePreparationError,
    StagePreparationResult,
)
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE
from app.state.transition_service import StateTransitionService, TransitionRequest


class StageExecutionError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


def bounded_idempotency_key(raw: str, max_length: int = 128) -> str:
    """Deterministically bound a backend-generated idempotency key.

    The command-policy DTO and the persistence layer both cap
    idempotency_key at 128 chars; stage continuation/attempt ids can push
    the composed key past that limit.  Short keys pass through untouched;
    longer keys get a SHA-256-derived suffix so the same raw key always
    yields the same bounded key (no randomness, no timestamps).
    """
    if len(raw) <= max_length:
        return raw
    suffix = ":" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return raw[: max_length - len(suffix)] + suffix


def validation_execution_key(
    continuation_id: str,
    attempt_key: str,
    group: str,
    command_index: int = 0,
) -> str:
    """Return the durable validation command identity.

    ValidationRunner historically includes the validation group in its
    request key, and the stage queue appends that group while deriving the
    command identity.  Keep that persisted grammar stable so recovery can
    address executions created before this helper existed.
    """
    raw = f"{continuation_id}:validation:{attempt_key}:{group}:{group}"
    if command_index:
        raw += f":{command_index}"
    return bounded_idempotency_key(raw)


def migration_attempt_key(migration_identity: str) -> str:
    """Canonical migration attempt key: migrate:<canonical_migration_identity>."""
    return f"migrate:{migration_identity}"


def expected_migrate_execution_idempotency_key(
    continuation_id: str,
    stage_id: str,
    migration_identity: str,
    package: str,
    from_version: str,
    to_version: str,
) -> str:
    """Derive the exact persisted CommandExecution.idempotency_key for a migrate-only command.

    Must use the SAME bounded helper and grammar as the governed queue path:
      continuation.id + stage_id + command + attempt_key  → bounded_idempotency_key
    where attempt_key = migrate:<identity>:<package>:<from>-><to>
    and final raw = <continuation>:<stage>:command:<dynamic_key>:migrate_packages
    """
    attempt_key = migration_attempt_key(migration_identity)
    dynamic_key = f"{attempt_key}:{package}:{from_version}->{to_version}"
    raw = f"{continuation_id}:{stage_id}:command:{dynamic_key}:migrate_packages"
    return bounded_idempotency_key(raw)


@dataclass(frozen=True)
class _ValidatedStageStart:
    run_id: str
    stage_id: str
    actor: str
    request: object
    plan: MigrationPlanModel
    stage: StageExecutionPlanModel
    artifact_set_checksum: str
    aliases: dict[str, str]
    artifact_root: str | None


class StageExecutionApplicationService:
    def __init__(self, *, scope=session_scope, now_provider=None, preparation=None, policy_engine=None, command_executor=None):
        self._scope = scope
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._preparation = preparation or StagePreparationApplicationService()
        self._policy_engine = policy_engine or CommandPolicyEngineService()
        self._command_executor = command_executor or CommandExecutorService(policy_engine=self._policy_engine)

    def start(self, run_id: str, stage_id: str, request, actor: str):
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageExecutionError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
            if run.actor != actor:
                raise StageExecutionError("RUN_NOT_AUTHORIZED", "The actor is not authorized for this run.", 403)
            existing = session.scalar(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key == request.idempotency_key,
                )
            )
            if existing:
                return self._result(run, stage_id, request, existing.sequence, True)
            if run.state_version != request.expected_state_version:
                raise StageExecutionError("STALE_STATE_VERSION", "The run state version is stale.")
            from app.repositories.models import TransformationContinuationModel
            from app.services.transformation_continuation_service import (
                TransformationContinuationError,
                TransformationContinuationService,
            )
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id,
                    TransformationContinuationModel.current_stage_id == stage_id,
                )
            )
            if continuation is None:
                raise StageExecutionError(
                    "TRANSFORMATION_NOT_READY",
                    "Accepted G06 has not created the durable Transformer continuation.",
                )
            if (
                continuation.plan_checksum != request.plan_checksum
                or continuation.stage_plan_checksum != request.stage_plan_checksum
            ):
                raise StageExecutionError("STAGE_PLAN_STALE", "Legacy start bindings are stale.")
            try:
                TransformationContinuationService().wake(session, continuation.id, now=self._now())
            except TransformationContinuationError as error:
                raise StageExecutionError(error.code, error.message) from error
            event = StateTransitionService(session).append_audit_event(
                run_id=run_id,
                idempotency_key=request.idempotency_key,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                actor=actor,
                reason="legacy stage-start delegated to durable Transformer",
                occurred_at=self._now(),
                payload={"stage_id": stage_id, "continuation_id": continuation.id},
            )
            return self._result(
                run,
                stage_id,
                request,
                event.event_sequence,
                False,
                run.state_version,
                continuation.plan_checksum,
                continuation.stage_plan_checksum,
            )

    def _validate(self, session, run_id, stage_id, request, actor) -> _ValidatedStageStart:
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise StageExecutionError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.actor != actor:
            raise StageExecutionError("RUN_NOT_AUTHORIZED", "The actor is not authorized for this run.", 403)
        if request.expected_state_version != run.state_version:
            raise StageExecutionError("STALE_STATE_VERSION", "The run state version is stale.")
        pointer = session.scalar(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == stage_id))
        if pointer is None:
            raise StageExecutionError("STAGE_PLAN_NOT_FOUND", "The requested stage has no active plan.", 404)
        plan = session.get(MigrationPlanModel, pointer.migration_plan_id)
        stage = session.get(StageExecutionPlanModel, pointer.stage_plan_id)
        gate = session.scalar(select(G06ApprovalModel).where(G06ApprovalModel.run_id == run_id, G06ApprovalModel.gate_id == "G06").order_by(G06ApprovalModel.state_version.desc(), G06ApprovalModel.created_at.desc()))
        if not plan or not stage or not gate:
            raise StageExecutionError("G06_APPROVAL_REQUIRED", "An approved current G06 gate is required before stage start.")
        checksums = {}
        for artifact_id in gate.artifact_ids or []:
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
            if metadata is None or metadata.run_id != run_id:
                raise StageExecutionError("G06_PACKAGE_INTEGRITY_FAILED", "A G06 artifact is unavailable.")
            checksums[artifact_id] = metadata.checksum
        aggregate = self.aggregate_artifact_checksum(checksums)
        if aggregate != request.artifact_set_checksum:
            raise StageExecutionError("ARTIFACT_SET_CHECKSUM_MISMATCH", "The current artifact set checksum is stale.")
        try:
            PlanRevisionService().require_approved_g06(
                gate,
                state_version=run.state_version,
                artifact_set_checksum=gate.artifact_set_checksum,
                plan_checksum=plan.checksum,
                stage_plan_checksum=stage.checksum,
                workspace_fingerprint=request.workspace_fingerprint,
            )
        except PlanningReviewApplicationError as error:
            raise StageExecutionError(error.code, error.message, error.status_code) from error
        return _ValidatedStageStart(run_id, stage_id, actor, request, plan, stage, aggregate, dict(run.workspace_aliases or {}), run.artifact_root)

    def _reload_and_validate(self, session, run, stage_id, request, actor):
        validated = self._validate(session, run.id, stage_id, request, actor)
        return validated.plan, validated.stage, session.scalar(select(G06ApprovalModel).where(G06ApprovalModel.run_id == run.id, G06ApprovalModel.gate_id == "G06").order_by(G06ApprovalModel.state_version.desc(), G06ApprovalModel.created_at.desc())), validated.artifact_set_checksum

    def _prepare_workspace(
        self,
        validated: _ValidatedStageStart,
        expected_fingerprint: str | None = None,
    ) -> StagePreparationResult:
        try:
            return self._preparation.prepare(
                validated.aliases,
                validated.stage_id,
                expected_fingerprint=expected_fingerprint,
                expected_source_fingerprint=validated.aliases.get("BASELINE_SANDBOX_FINGERPRINT"),
            )
        except StagePreparationError as error:
            raise StageExecutionError(error.code, error.message, 409) from error
        except Exception as error:
            raise StageExecutionError("STAGE_PREPARATION_FAILED", "Stage workspace preparation failed; no stage was marked successful.", 409) from error

    def _write_preparation_artifacts(self, validated: _ValidatedStageStart, preparation: StagePreparationResult):
        now = self._now()
        root = Path(validated.artifact_root or (Path(preparation.workspace_path).parent / "artifacts"))
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        payload = {
            "stage_id": validated.stage_id,
            "workspace_alias": preparation.workspace_alias,
            "workspace_path": preparation.workspace_path,
            "workspace_fingerprint": preparation.fingerprint,
            "copied_files": preparation.copied_files,
        }
        report = store.write_text_artifact(
            validated.run_id,
            f"04_workflow_state/stages/{validated.stage_id}/stage-preparation.json",
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=validated.stage_id,
            created_by="stage-execution-application-service",
            created_at=now,
            input_hashes={"stage_plan": validated.stage.checksum},
            policy_version="stage-preparation-v1",
        )
        fingerprint = store.write_text_artifact(
            validated.run_id,
            f"04_workflow_state/stages/{validated.stage_id}/stage-workspace-fingerprint.json",
            json.dumps(
                {
                    "stage_id": validated.stage_id,
                    "workspace_alias": preparation.workspace_alias,
                    "workspace_fingerprint": preparation.fingerprint,
                },
                sort_keys=True,
                indent=2,
            ),
            ArtifactType.JSON,
            stage_id=validated.stage_id,
            created_by="stage-execution-application-service",
            created_at=now,
            input_hashes={"stage_plan": validated.stage.checksum},
            policy_version="stage-preparation-v1",
        )
        return report, fingerprint

    def _persist_prepared_stage(self, session, run, stage_id, stage, preparation, preparation_artifacts):
        now = self._now()
        stage_value = stage.stage_plan or {}
        stage_record = session.get(MigrationStageModel, stage_id)
        if stage_record is None:
            session.add(MigrationStageModel(
                id=stage_id,
                run_id=run.id,
                stage_order=session.query(MigrationStageModel).filter(MigrationStageModel.run_id == run.id).count() + 1,
                source_version_family=stage_value.get("source_family"),
                target_version_family=stage_value.get("target_family"),
                source_version_detected=stage_value.get("source_exact"),
                target_version_resolved=stage_value.get("target_exact"),
                source_angular_version=stage_value.get("source_exact"),
                target_angular_version=stage_value.get("target_exact"),
                status="prepared",
                created_at=now,
            ))
        else:
            if stage_record.run_id != run.id:
                raise StageExecutionError(
                    "STAGE_ID_OWNERSHIP_CONFLICT",
                    "The planned stage belongs to another migration run.",
                    409,
                )
            stage_record.source_version_family = stage_value.get("source_family") or stage_record.source_version_family
            stage_record.target_version_family = stage_value.get("target_family") or stage_record.target_version_family
            stage_record.source_version_detected = stage_value.get("source_exact") or stage_record.source_version_detected
            stage_record.target_version_resolved = stage_value.get("target_exact") or stage_record.target_version_resolved
            stage_record.source_angular_version = stage_value.get("source_exact") or stage_record.source_angular_version
            stage_record.target_angular_version = stage_value.get("target_exact") or stage_record.target_angular_version
            stage_record.status = "prepared"
        aliases = dict(run.workspace_aliases or {})
        aliases[preparation.workspace_alias] = preparation.workspace_path
        run.workspace_aliases = aliases
        binding = session.scalar(
            select(StageWorkspaceBindingModel)
            .where(
                StageWorkspaceBindingModel.run_id == run.id,
                StageWorkspaceBindingModel.stage_id == stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
            .order_by(
                StageWorkspaceBindingModel.created_at.desc(),
                StageWorkspaceBindingModel.id.desc(),
            )
        )
        if binding is None:
            binding = StageWorkspaceBindingModel(
                id="stage-workspace-" + hashlib.sha256(
                    f"{run.id}:{stage_id}:{preparation.workspace_alias}".encode()
                ).hexdigest()[:24],
                run_id=run.id,
                stage_id=stage_id,
                alias=preparation.workspace_alias,
                workspace_path=preparation.workspace_path,
                workspace_fingerprint=preparation.fingerprint,
                fingerprint_profile_id=STAGE_FINGERPRINT_PROFILE.profile_id,
                input_fingerprint=preparation.fingerprint,
                active=True,
                created_at=now,
            )
            session.add(binding)
        generation = None
        if binding.workspace_generation_id:
            generation = session.get(WorkspaceGenerationModel, binding.workspace_generation_id)
        if generation is None:
            current_generation = session.scalar(
                select(WorkspaceGenerationModel.generation)
                .where(
                    WorkspaceGenerationModel.run_id == run.id,
                    WorkspaceGenerationModel.stage_id == stage_id,
                    WorkspaceGenerationModel.alias == binding.alias,
                )
                .order_by(WorkspaceGenerationModel.generation.desc())
                .limit(1)
            ) or 0
            generation_number = current_generation + 1
            generation_id = "gen-" + hashlib.sha256(
                f"{run.id}:{stage_id}:{binding.alias}:{generation_number}".encode()
            ).hexdigest()[:24]
            generation = WorkspaceGenerationModel(
                id=generation_id,
                run_id=run.id,
                stage_id=stage_id,
                alias=binding.alias,
                generation=generation_number,
                workspace_path=binding.workspace_path,
                fingerprint=binding.workspace_fingerprint,
                input_fingerprint=binding.input_fingerprint,
                status="prepared",
                active_binding_id=binding.id,
                created_at=now,
            )
            session.add(generation)
            binding.workspace_generation_id = generation.id
        current_steps = session.query(StageStepModel).filter(
            StageStepModel.stage_plan_id == stage.id,
            StageStepModel.workspace_generation_id == generation.id,
        ).count()
        if current_steps == 0:
            for group, references in (stage.stage_plan.get("commands") or {}).items():
                for index, _reference in enumerate(references if isinstance(references, list) else (references,)):
                    session.add(StageStepModel(
                        id=f"step-{run.id}-{stage_id}-{stage.id[:16]}-{group}-{index}",
                        run_id=run.id,
                        stage_id=stage_id,
                        stage_plan_id=stage.id,
                        workspace_generation_id=generation.id,
                        step_key=f"{group}-{index}",
                        projection_version=1,
                        source_record_type="command_execution",
                        name=f"{group}-{index}",
                        status="PENDING",
                        component_type="command",
                        idempotency_key=f"{run.id}:{stage_id}:{stage.id}:{group}:{index}",
                    ))
        for artifact in preparation_artifacts:
            session.add(ArtifactMetadataModel(
                id="metadata-" + artifact.ref.artifact_id,
                run_id=run.id,
                stage_id=stage_id,
                artifact_type=artifact.ref.artifact_type.value,
                relative_path=artifact.ref.relative_path,
                checksum=artifact.ref.checksum,
                created_at=artifact.ref.created_at,
                finalized_at=artifact.ref.created_at,
                immutable=True,
            ))
        session.flush()

    def _record_preparation_events(self, session, run, stage_id, request, actor, preparation) -> None:
        transitions = StateTransitionService(session)
        for suffix, event_type, reason, payload in (
            ("preparation-started", WorkflowEventType.STAGE_PREPARATION_STARTED, "stage preparation started", {}),
            ("sandbox-copied", WorkflowEventType.STAGE_SANDBOX_COPIED, "contained stage sandbox copied", {"workspace_fingerprint": preparation.fingerprint}),
            ("workspace-bound", WorkflowEventType.STAGE_WORKSPACE_BOUND, "stage workspace alias bound", {"workspace_alias": preparation.workspace_alias}),
            ("preparation-completed", WorkflowEventType.STAGE_PREPARATION_COMPLETED, "stage preparation completed", {"workspace_alias": preparation.workspace_alias, "workspace_fingerprint": preparation.fingerprint}),
        ):
            transitions.append_audit_event(
                run_id=run.id,
                idempotency_key=f"{request.idempotency_key}:{suffix}",
                event_type=event_type,
                actor=actor,
                reason=reason,
                occurred_at=self._now(),
                payload={"stage_id": stage_id, **payload},
            )

    def _authorize_and_queue_first_command(
        self,
        session,
        run,
        plan,
        stage,
        preparation,
        request,
        actor,
        group="bootstrap_install",
        command_index=0,
        persisted_idempotency_key=None,
        parameter_bindings_override=None,
        reference_override=None,
    ):
        stage_plan = stage.stage_plan or {}
        references = (stage_plan.get("commands") or {}).get(group) or []
        if reference_override is None and not references:
            raise StageExecutionError(
                "STAGE_COMMAND_NOT_FOUND",
                f"The approved stage plan contains no {group} command.",
            )
        if reference_override is None and command_index >= len(references):
            raise StageExecutionError("STAGE_COMMAND_NOT_FOUND", f"{group} command index is invalid.")
        reference = reference_override or references[command_index]
        # P0-2: dynamic migrate-only bindings — keep template authority but bind exact package/from/to
        if group == "migrate_packages" and isinstance(parameter_bindings_override, dict) and parameter_bindings_override:
            # Validate that plan authorizes the migrate-range template at all
            if reference.get("command_id") != "angular-migrate-range" or reference.get("template_id") != "tpl-angular-migrate-range-v1":
                raise StageExecutionError("MIGRATE_RANGE_TEMPLATE_NOT_AUTHORIZED", "Stage plan does not authorize angular-migrate-range template")
            from app.domain.command import ANGULAR_MIGRATE_RANGE_RENDERER

            try:
                rendered = list(ANGULAR_MIGRATE_RANGE_RENDERER.render_arguments(parameter_bindings_override))
            except ValueError as error:
                raise StageExecutionError("MIGRATE_RANGE_BINDING_INVALID", str(error)) from error
            # Build dynamic reference preserving template identity but with exact bindings
            reference = {
                **reference,
                "parameter_bindings": dict(parameter_bindings_override),
                "arguments": rendered,
            }
        profile_id = stage_plan.get("execution_profile_id")
        if not isinstance(profile_id, str) or not profile_id:
            raise StageExecutionError("EXECUTION_PROFILE_NOT_APPROVED", "The approved stage plan has no execution profile.")
        if persisted_idempotency_key is None:
            continuation_key = f"{request.idempotency_key}:{group}"
            if command_index:
                continuation_key += f":{command_index}"
            continuation_key = bounded_idempotency_key(continuation_key)
        else:
            continuation_key = persisted_idempotency_key
        CommandRegistryService().seed_defaults(session)
        try:
            policy_request = CommandPolicyValidateRequestDto(
                run_id=run.id,
                expected_state_version=run.state_version,
                stage_id=stage.stage_id,
                plan_id=plan.id,
                plan_version=stage.version,
                command_id=reference["command_id"],
                template_id=reference["template_id"],
                template_version=reference["template_version"],
                executable=reference["executable"],
                arguments=list(reference.get("arguments") or []),
                cwd_alias=preparation.workspace_alias,
                working_directory_alias=preparation.workspace_alias,
                working_directory=preparation.workspace_path,
                execution_profile_id=profile_id,
                network_profile=reference["network_profile"],
                timeout_seconds=reference["timeout_seconds"],
                idempotency_key=continuation_key,
                requested_by=actor,
            )
        except ValidationError as error:
            field = error.errors()[0]["loc"][0] if error.errors() else "request"
            raise StageExecutionError(
                "COMMAND_POLICY_REQUEST_INVALID",
                f"Internally generated command-policy request is invalid: {field}.",
            ) from error
        try:
            authorization = self._policy_engine.validate(
                session,
                policy_request,
            )
        except CommandPolicyError as error:
            raise StageExecutionError(error.code, error.message) from error
        if authorization.decision != "accepted":
            raise StageExecutionError("FIRST_COMMAND_NOT_AUTHORIZED", "The first planned command was rejected by command policy.")
        try:
            return self._command_executor.queue_authorized_command(
                session,
                run_id=run.id,
                authorization_decision_id=authorization.authorization_id,
                expected_state_version=run.state_version,
                idempotency_key=continuation_key,
                requested_by=actor,
                correlation_id=authorization.correlation_id,
                timeout_seconds=reference["timeout_seconds"],
            )
        except CommandExecutorError as error:
            raise StageExecutionError(error.code, error.message) from error

    @staticmethod
    def aggregate_artifact_checksum(checksums: dict[str, str]) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(dict(sorted(checksums.items())), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _result(run, stage_id, request, event_sequence, replay, state_version=None, plan_checksum=None, stage_checksum=None, aggregate=None, workspace_fingerprint=None, authorization_id=None, execution_id=None):
        return {
            "run_id": run.id,
            "stage_id": stage_id,
            "status": RunStatus.STAGE_CREATED.value,
            "plan_checksum": plan_checksum or request.plan_checksum,
            "stage_plan_checksum": stage_checksum or request.stage_plan_checksum,
            "artifact_set_checksum": aggregate or request.artifact_set_checksum,
            "state_version": state_version or run.state_version,
            "event_sequence": event_sequence,
            "idempotent_replay": replay,
            "workspace_fingerprint": workspace_fingerprint,
            "first_command_authorization_id": authorization_id,
            "first_command_execution_id": execution_id,
        }
