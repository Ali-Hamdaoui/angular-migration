"""Approved-stage preparation, preflight, and frozen command helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.command import ANGULAR_UPDATE_V2_RENDERER, ANGULAR_UPDATE_V3_RENDERER
from app.domain.runtime_execution import RuntimeExecutableKind, RuntimeExecutableDescriptor
from app.domain.contracts import ArtifactType, RunStatus, WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairFingerprintRecoveryModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageReconstructionRecordModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    StageRuntimeBindingModel,
    TransformationContinuationModel,
)
from app.repositories.session import session_scope
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
)
from app.services.stage_execution_application_service import (
    StageExecutionApplicationService,
    StageExecutionError,
    _ValidatedStageStart,
)
from app.services.stage_preparation_application_service import StagePreparationResult
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.stage_runtime_service import StageRuntimeApplicationService, StageRuntimeError
from app.services.transformation_continuation_service import (
    append_continuation_event,
)
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE
from app.services.workspace_fingerprint import LEGACY_STAGE_COMPLETE_FINGERPRINT_PROFILE
from app.state import StateTransitionService, TransitionRequest


class TransformerStageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def artifact_metadata_id(artifact_id: str) -> str:
    """Artifact metadata primary key binding for an immutable artifact id.

    The row primary key keeps the codebase-wide ``"metadata-" + artifact_id``
    contract (consumers strip the prefix and look rows up by artifact id), while
    exactly-once semantics are enforced by the pending-aware registration guard
    and by committed-evidence replay keyed on the failure fingerprint.
    """
    return "metadata-" + artifact_id


class TransformerStageService:
    def __init__(
        self,
        *,
        scope=session_scope,
        stage_execution=None,
        command_executor=None,
        stage_runtime_service=None,
        now_provider=None,
    ) -> None:
        self._scope = scope
        self._stage_execution = stage_execution or StageExecutionApplicationService(scope=scope)
        self._command_executor = command_executor or CommandExecutorService()
        self._stage_runtime = stage_runtime_service or StageRuntimeApplicationService()
        self._now = now_provider or (lambda: datetime.now(UTC))

    def prepare(self, continuation_id: str, worker_id: str) -> str:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            run = session.get(MigrationRunModel, continuation.run_id)
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            gate = session.get(G06ApprovalModel, continuation.g06_approval_id)
            if not run or not plan or not stage_plan or not gate:
                raise TransformerStageError("G06_BINDING_STALE", "Approved stage binding is missing")
            request = self._request(run, continuation, gate)
            validated = _ValidatedStageStart(
                run.id,
                continuation.current_stage_id,
                run.actor or "transformer",
                request,
                plan,
                stage_plan,
                gate.artifact_set_checksum,
                dict(run.workspace_aliases or {}),
                run.artifact_root,
            )
            durable = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run.id,
                    StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            expected_fingerprint = durable.workspace_fingerprint if durable is not None else None
        try:
            preparation = self._stage_execution._prepare_workspace(
                validated, expected_fingerprint=expected_fingerprint
            )
            artifacts = self._stage_execution._write_preparation_artifacts(validated, preparation)
        except StageExecutionError as error:
            raise TransformerStageError(error.code, error.message) from error
        try:
            pre_bootstrap_snapshot = self.snapshot_workspace(
                preparation.workspace_path,
                validated.aliases['STAGE_SANDBOX'],
                validated.stage_id,
            )
        except TransformerStageError:
            raise
        except Exception as error:
            raise TransformerStageError(
                'PRE_BOOTSTRAP_CHECKPOINT_MISSING',
                'The immutable pre_bootstrap checkpoint could not be created.',
            ) from error
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            run = session.get(MigrationRunModel, continuation.run_id)
            if run.state_version != request.expected_state_version:
                raise TransformerStageError("STALE_STATE_VERSION", "Run changed during workspace preparation")
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            self._stage_execution._persist_prepared_stage(
                session, run, continuation.current_stage_id, stage_plan, preparation, artifacts
            )
            StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run.id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=WorkflowEventType.STAGE_CREATED,
                    next_run_status=RunStatus.STAGE_CREATED,
                    actor=run.actor or "transformer",
                    reason="durable Transformer prepared the approved stage workspace",
                    stage_id=continuation.current_stage_id,
                    payload={
                        "plan_checksum": continuation.plan_checksum,
                        "stage_plan_checksum": continuation.stage_plan_checksum,
                        "workspace_alias": preparation.workspace_alias,
                        "workspace_fingerprint": preparation.fingerprint,
                    },
                    occurred_at=self._now(),
                )
            )
            self._stage_execution._record_preparation_events(
                session,
                run,
                continuation.current_stage_id,
                request,
                run.actor or "transformer",
                preparation,
            )
            input_checkpoint = self._checkpoint(
                session,
                continuation,
                pre_bootstrap_snapshot,
                "pre_bootstrap",
                artifacts[-1].ref.artifact_id,
                artifacts[-1].ref.checksum,
            )
            binding = self._binding(session, continuation)
            binding.source_checkpoint_id = input_checkpoint.id
            self._advance(continuation, "resolve_runtime")
            return preparation.fingerprint

    def runtime_binding(self, session, continuation: TransformationContinuationModel) -> dict[str, object]:
        stage_runtime = self._stage_runtime_rows(session, continuation)
        if stage_runtime is not None:
            return stage_runtime
        evidence, selected = self.runtime_binding_evidence(session, continuation)
        if evidence["mismatches"]:
            raise TransformerStageError(
                "EXECUTION_PROFILE_STALE",
                "Selected execution profile no longer matches the approved stage plan: "
                + json.dumps(evidence, sort_keys=True, separators=(",", ":")),
            )
        return {
            "profile_id": evidence["actual"]["profile_id"],
            "checksum": evidence["actual"]["checksum"],
            "node_executable": selected.get("node_executable"),
            "package_manager_executable": selected.get("package_manager_executable", "npm"),
        }

    def resolve_stage_runtime(self, session, continuation: TransformationContinuationModel) -> dict[str, object]:
        """Resolve and persist the exact runtime binding for this stage."""
        stage = session.get(MigrationStageModel, continuation.current_stage_id)
        if stage is None:
            raise TransformerStageError("STAGE_NOT_FOUND", "The transformation stage is unavailable")
        try:
            binding = self._stage_runtime.resolve_stage(
                stage.id,
                stage.source_version_family or "",
                stage.target_version_family or "",
            )
            self._stage_runtime.record_binding(continuation.run_id, binding, actor="transformer")
        except StageRuntimeError as error:
            raise TransformerStageError(error.code, error.message) from error
        if binding.status != "bound":
            raise TransformerStageError(
                "STAGE_RUNTIME_UNAVAILABLE",
                binding.blocked_reason or "No governed runtime satisfies this stage",
            )
        return self.runtime_binding(session, continuation)

    @staticmethod
    def _stage_runtime_rows(session, continuation: TransformationContinuationModel) -> dict[str, object] | None:
        """Read one complete durable stage binding; return None for legacy callers."""
        if not hasattr(session, "scalars") or not getattr(continuation, "current_stage_id", None):
            return None
        rows = list(
            session.scalars(
                select(StageRuntimeBindingModel)
                .where(StageRuntimeBindingModel.stage_id == continuation.current_stage_id)
                .order_by(StageRuntimeBindingModel.kind.asc())
            ).all()
        )
        if not rows:
            return None
        expected = {kind.value for kind in RuntimeExecutableKind}
        if {row.kind for row in rows} != expected or any(row.status != "bound" for row in rows):
            raise TransformerStageError("STAGE_RUNTIME_BINDING_STALE", "The durable stage runtime binding is incomplete or blocked")
        if len({row.runtime_id for row in rows}) != 1:
            raise TransformerStageError("STAGE_RUNTIME_BINDING_STALE", "Stage Node/npm/npx bindings do not share one installation")
        descriptors: dict[str, RuntimeExecutableDescriptor] = {}
        for row in rows:
            if not row.resolved_path or not row.version_exact or not row.sha256 or not row.runtime_id:
                raise TransformerStageError("STAGE_RUNTIME_BINDING_STALE", "The durable stage runtime binding is incomplete")
            try:
                kind = RuntimeExecutableKind(row.kind)
                descriptors[row.kind] = RuntimeExecutableDescriptor(
                    kind=kind,
                    executable_name=Path(row.resolved_path).name,
                    resolved_path=row.resolved_path,
                    version_exact=row.version_exact,
                    sha256=row.sha256,
                    installation_root=str(Path(row.resolved_path).parent),
                    source=row.source or "stage-runtime-binding",
                    runtime_id=row.runtime_id,
                    probed_at=row.created_at,
                )
            except (TypeError, ValueError) as error:
                raise TransformerStageError("STAGE_RUNTIME_BINDING_STALE", "The durable stage runtime binding is invalid") from error
        checksum = "sha256:" + hashlib.sha256(
            json.dumps(
                {key: value.model_dump(mode="json") for key, value in sorted(descriptors.items())},
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest()
        return {
            "profile_id": f"stage-runtime:{continuation.current_stage_id}",
            "checksum": checksum,
            "node_executable": descriptors[RuntimeExecutableKind.NODE.value].resolved_path,
            "package_manager_executable": descriptors[RuntimeExecutableKind.NPM.value].resolved_path,
            "npx_executable": descriptors[RuntimeExecutableKind.NPX.value].resolved_path,
            "runtime_bindings": {
                key: value.model_dump(mode="json") for key, value in descriptors.items()
            },
        }

    @staticmethod
    def runtime_binding_evidence(session, continuation: TransformationContinuationModel):
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        profile = session.scalar(
            select(ExecutionProfileModel)
            .where(ExecutionProfileModel.run_id == continuation.run_id)
            .order_by(ExecutionProfileModel.created_at.desc())
        )
        planned = stage_plan.stage_plan or {} if stage_plan else {}
        expected_id = planned.get("execution_profile_id")
        expected_checksums = sorted(
            {
                command.get("runtime_profile_checksum")
                for commands in (planned.get("commands") or {}).values()
                for command in commands
                if command.get("runtime_profile_checksum")
            }
        )
        selected = next(
            (
                item
                for item in (profile.profiles or [])
                if item.get("profile_id") == profile.selected_profile_id
            ),
            None,
        ) if profile else None
        actual = {
            "status": profile.status if profile else None,
            "profile_id": profile.selected_profile_id if profile else None,
            "checksum": profile.selected_checksum if profile else None,
            "persisted_profile_checksum": selected.get("checksum") if selected else None,
        }
        expected = {
            "statuses": ["resolved", "selected"],
            "profile_id": expected_id,
            "checksums": expected_checksums,
        }
        mismatches = []
        if actual["status"] not in expected["statuses"]:
            mismatches.append("status")
        if actual["profile_id"] != expected_id:
            mismatches.append("profile_id")
        if expected_checksums != [actual["checksum"]]:
            mismatches.append("checksum")
        if actual["persisted_profile_checksum"] != actual["checksum"]:
            mismatches.append("persisted_profile_checksum")
        return {"expected": expected, "actual": actual, "mismatches": mismatches}, selected

    def preflight(self, session, continuation: TransformationContinuationModel) -> dict[str, object]:
        binding = self._binding(session, continuation)
        workspace = Path(binding.workspace_path)
        package_path = workspace / "package.json"
        lock_path = workspace / "package-lock.json"
        blockers: list[str] = []
        if not package_path.is_file():
            blockers.append("PACKAGE_JSON_MISSING")
            package: dict[str, object] = {}
        else:
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                package = {}
                blockers.append("PACKAGE_JSON_INVALID")
        if not lock_path.is_file():
            blockers.append("PACKAGE_LOCK_MISSING")
        dependencies = {
            **(package.get("dependencies") or {}),
            **(package.get("devDependencies") or {}),
        }
        if any(
            isinstance(value, str) and value.startswith(("file:", "git:", "git+", "http:"))
            for value in dependencies.values()
        ):
            blockers.append("NON_REGISTRY_DEPENDENCY")
        npmrc = workspace / ".npmrc"
        if npmrc.is_file():
            text = npmrc.read_text(encoding="utf-8", errors="replace")
            if "legacy-peer-deps=true" in text.lower() or "force=true" in text.lower():
                blockers.append("FORCED_DEPENDENCY_RESOLUTION")
        return {
            "status": "blocked" if blockers else "compatible",
            "blockers": sorted(set(blockers)),
            "package_manager": (package.get("packageManager") or "npm"),
            "workspace_fingerprint": binding.workspace_fingerprint,
        }

    def known_decisions(self, session, continuation: TransformationContinuationModel) -> dict[str, object]:
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        value = stage_plan.stage_plan or {}
        return {
            "build_system_decision": value.get("build_system_decision"),
            "validation_policy": value.get("validation_policy"),
            "recovery_policy": value.get("recovery_policy"),
            "repair_policy": value.get("repair_policy"),
            "forbidden_change_policy": value.get("forbidden_change_policy"),
        }

    def write_gate_package(
        self,
        *,
        run_id: str,
        stage_id: str,
        artifact_root: str,
        gate_id: str,
        payload: dict[str, object],
        attempt_id: str | None = None,
    ):
        now = self._now()
        run_root = Path(artifact_root)
        store = LocalFilesystemArtifactStore(run_root.parent, fixed_run_root=run_root)
        return store.write_text_artifact(
            run_id,
            f"04_workflow_state/stages/{stage_id}/gates/{gate_id.lower()}-package.json",
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=stage_id,
            attempt_id=attempt_id,
            created_by="transformer",
            created_at=now,
            input_hashes={"stage_plan": str(payload["stage_plan_checksum"])},
            policy_version="transformer-gate-v1",
        )

    @staticmethod
    def register_artifact(session, stored, continuation: TransformationContinuationModel) -> None:
        metadata_id = artifact_metadata_id(stored.ref.artifact_id)
        committed = session.get(ArtifactMetadataModel, metadata_id)
        if committed is not None:
            TransformerStageService._validate_committed_metadata(committed, continuation, stored)
            return
        for pending in (*session.new, *session.dirty):
            if isinstance(pending, ArtifactMetadataModel) and pending.id == metadata_id:
                return
        session.add(
            ArtifactMetadataModel(
                id=metadata_id,
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                schema_version=stored.envelope.schema_version,
                created_at=stored.ref.created_at,
                finalized_at=stored.ref.created_at,
                immutable=True,
                size_bytes=len(stored.content.encode("utf-8")),
            )
        )

    @staticmethod
    def _validate_committed_metadata(committed, continuation, stored) -> None:
        mismatches = []
        if committed.run_id != continuation.run_id:
            mismatches.append(f"run_id (expected {continuation.run_id}, stored {committed.run_id})")
        if committed.stage_id != continuation.current_stage_id:
            mismatches.append(
                f"stage_id (expected {continuation.current_stage_id}, stored {committed.stage_id})"
            )
        if committed.artifact_type != stored.ref.artifact_type.value:
            mismatches.append(
                f"artifact_type (expected {stored.ref.artifact_type.value}, stored {committed.artifact_type})"
            )
        if committed.relative_path != stored.ref.relative_path:
            mismatches.append(
                f"relative_path (expected {stored.ref.relative_path}, stored {committed.relative_path})"
            )
        if committed.checksum != stored.ref.checksum:
            mismatches.append(f"checksum (expected {stored.ref.checksum}, stored {committed.checksum})")
        if mismatches:
            raise TransformerStageError(
                "ARTIFACT_METADATA_IDENTITY_CONFLICT",
                "Committed artifact metadata for the same artifact id carries a different payload: "
                + "; ".join(mismatches),
            )

    def queue_bootstrap(self, session, continuation: TransformationContinuationModel):
        binding = self._binding(session, continuation)
        checkpoint = session.get(StageCheckpointModel, binding.source_checkpoint_id)
        if (
            checkpoint is None
            or checkpoint.run_id != continuation.run_id
            or checkpoint.stage_id != continuation.current_stage_id
            or checkpoint.kind != 'pre_bootstrap'
            or self.authoritative_checkpoint_fingerprint(session, checkpoint) is None
        ):
            raise TransformerStageError(
                'PRE_BOOTSTRAP_CHECKPOINT_MISSING',
                'Bootstrap cannot start without the authoritative pre_bootstrap checkpoint.',
            )
        return self._queue_group(
            session,
            continuation,
            group="bootstrap_install",
            next_node="verify_bootstrap",
            attempt_key="initial",
            checkpoint_id=checkpoint.id,
        )

    def queue_angular_update(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        checkpoint_id: str,
        prompt_id: str | None,
    ):
        return self._queue_group(
            session,
            continuation,
            group="angular_update",
            next_node="handle_prompt",
            attempt_key=prompt_id or "initial",
            checkpoint_id=checkpoint_id,
            prompt_id=prompt_id,
        )

    def queue_angular_update_retry(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        failed_execution_id: str,
        idempotency_key: str,
    ):
        """Queue one governed successor for the failed angular update command.

        The successor reuses the failed execution's immutable lineage. A
        legacy accepted Angular v2 command is explicitly superseded by one
        newly authorized v3 command; the terminal failed row is never mutated
        or replayed. The workspace must be the governed post-repair workspace:
        its live fingerprint must equal the durable binding, which the apply
        already updated to the post-repair fingerprint.
        """
        failed = session.get(CommandExecutionModel, failed_execution_id)
        if (
            failed is None
            or failed.run_id != continuation.run_id
            or failed.stage_id != continuation.current_stage_id
        ):
            raise TransformerStageError(
                "ANGULAR_UPDATE_RETRY_INVALID",
                "Failed angular update execution does not belong to this run and stage",
            )
        binding = self._binding(session, continuation)
        live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
        if live != binding.workspace_fingerprint:
            raise TransformerStageError(
                "ANGULAR_UPDATE_RETRY_REQUIRES_RECOVERY",
                "Post-repair workspace is not the governed workspace fingerprint",
            )
        failed = session.get(CommandExecutionModel, failed_execution_id)
        replacement_authorization_id = None
        retry_checkpoint_id = None
        if (
            failed is not None
            and failed.command_id == "angular-update-exact"
            and failed.template_version == 2
        ):
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            stage_data = (stage_plan.stage_plan or {}) if stage_plan is not None else {}
            references = ((stage_data.get("commands") or {}).get("angular_update") or [])
            planned = references[0] if len(references) == 1 else None
            bindings = (planned or {}).get("parameter_bindings") or {}
            try:
                failed_arguments_match = (
                    tuple(failed.arguments or [])
                    == ANGULAR_UPDATE_V2_RENDERER.render_arguments(bindings)
                )
                retry_arguments = ANGULAR_UPDATE_V3_RENDERER.render_arguments(bindings)
            except (TypeError, ValueError) as error:
                raise TransformerStageError(
                    "ANGULAR_UPDATE_RETRY_INVALID",
                    "The accepted v2 Angular command authority cannot be superseded",
                ) from error
            if (
                planned is None
                or planned.get("command_id") != "angular-update-exact"
                or planned.get("template_id") != ANGULAR_UPDATE_V2_RENDERER.template_id
                or planned.get("template_version") != 2
                or not failed_arguments_match
            ):
                raise TransformerStageError(
                    "ANGULAR_UPDATE_RETRY_INVALID",
                    "The accepted v2 Angular command authority cannot be superseded",
                )
            retry_checkpoint = session.scalar(
                select(StageCheckpointModel)
                .where(
                    StageCheckpointModel.run_id == continuation.run_id,
                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                    StageCheckpointModel.kind == "post_repair",
                )
                .order_by(StageCheckpointModel.sequence.desc())
            )
            if retry_checkpoint is None:
                raise TransformerStageError(
                    "POST_REPAIR_CHECKPOINT_MISSING",
                    "Angular v3 recovery requires the durable post-repair checkpoint",
                )
            retry_checkpoint_id = retry_checkpoint.id
            try:
                replacement_authorization_id = self._command_executor.authorize_retry_command(
                    session,
                    failed_execution_id,
                    template_id=ANGULAR_UPDATE_V3_RENDERER.template_id,
                    template_version=3,
                    executable=ANGULAR_UPDATE_V3_RENDERER.executable,
                    arguments=list(retry_arguments),
                    working_directory_alias=binding.alias,
                    working_directory=binding.workspace_path,
                    plan_id=failed.plan_id or continuation.plan_id,
                    plan_version=failed.plan_version or stage_data.get("plan_version") or 1,
                    execution_profile_id=str(stage_data.get("execution_profile_id") or ""),
                    network_profile=ANGULAR_UPDATE_V3_RENDERER.network_profile,
                    timeout_seconds=ANGULAR_UPDATE_V3_RENDERER.timeout_seconds,
                    idempotency_key=f"{failed_execution_id}:supersession:angular-v3",
                )
            except CommandExecutorError as error:
                raise TransformerStageError(error.code, error.message) from error
        elif failed is not None and failed.template_version == 3:
            # A v3 retry binds the newest post-repair checkpoint (the tree the
            # retry actually runs on) so interruption recovery restores the
            # correct state; absent one, the failed execution's own checkpoint
            # remains the fallback.
            retry_checkpoint = session.scalar(
                select(StageCheckpointModel)
                .where(
                    StageCheckpointModel.run_id == continuation.run_id,
                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                    StageCheckpointModel.kind == "post_repair",
                )
                .order_by(StageCheckpointModel.sequence.desc())
            )
            if retry_checkpoint is not None:
                retry_checkpoint_id = retry_checkpoint.id
        try:
            result = self._command_executor.queue_retry_execution(
                session,
                failed_execution_id,
                idempotency_key=idempotency_key,
                workspace_recovered=True,
                replacement_authorization_id=replacement_authorization_id,
                checkpoint_id=retry_checkpoint_id,
                authorized_timeout_seconds=ANGULAR_UPDATE_V3_RENDERER.timeout_seconds,
            )
        except CommandExecutorError as error:
            raise TransformerStageError(error.code, error.message) from error
        successor = session.get(CommandExecutionModel, result.execution_id)
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        if step is not None:
            step.execution_id = successor.id
            step.attempt_id = successor.id
            step.status = "RUNNING"
            step.updated_at = self._now()
        expected_state_version = continuation.state_version
        continuation.status = "waiting_command"
        continuation.current_node = "handle_prompt"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.waiting_execution_id = successor.id
        continuation.state_version += 1
        continuation.updated_at = self._now()
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
            key=f"wait:waiting_command:{expected_state_version}",
            reason="governed angular update retry queued after repair apply",
            payload={
                "execution_id": successor.id,
                "parent_execution_id": failed_execution_id,
                "expected_state_version": expected_state_version,
            },
        )
        return result

    def queue_version_check(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        attempt_key: str,
        recovery_of: str | None = None,
    ):
        return self._queue_group(
            session,
            continuation,
            group="target_version_check",
            next_node="version_verify",
            attempt_key=attempt_key,
            recovery_of=recovery_of,
        )

    def queue_lockfile_generation(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        attempt_key: str,
    ):
        return self._queue_group(
            session,
            continuation,
            group="lockfile_generation",
            next_node="lockfile_generation",
            attempt_key=attempt_key,
        )

    def snapshot_workspace(self, workspace_path: str, stage_root: str, stage_id: str) -> StagePreparationResult:
        """Record a lightweight checkpoint of the one mutable stage workspace.

        New stages never duplicate the application tree.  The checkpoint row
        persists the canonical fingerprint and immutable artifact lineage;
        legacy rows that already point at a separate snapshot remain readable
        by the recovery code below.
        """
        workspace = Path(workspace_path).resolve(strict=True)
        root = Path(stage_root).resolve(strict=True)
        workspace.relative_to(root)
        if any(item.is_symlink() for item in workspace.rglob("*")):
            raise TransformerStageError("WORKSPACE_SYMLINK_UNSUPPORTED", "Checkpoint source contains a symlink")
        return StagePreparationResult(
            "STAGE_WORKSPACE_" + stage_id.upper().replace("-", "_"),
            str(workspace),
            StageSandboxCopier.fingerprint(workspace),
            0,
            False,
        )

    def persist_snapshot_checkpoint(
        self,
        session,
        continuation,
        snapshot: StagePreparationResult,
        kind: str,
    ) -> StageCheckpointModel:
        # A checkpoint used by Angular update evidence must outlive mutations
        # to the active stage workspace. Keep the checkpoint tree under the
        # run's governed artifact root so the pre/post manifest comparison is
        # against an immutable pre-command copy rather than the same mutable
        # directory after `ng update`.
        run = session.get(MigrationRunModel, continuation.run_id)
        if run is None or not run.artifact_root:
            raise TransformerStageError(
                "CHECKPOINT_ROOT_MISSING",
                "The run artifact root is required for an immutable checkpoint",
            )
        artifact_root = Path(run.artifact_root).resolve(strict=True)
        checkpoint_parent = artifact_root / "checkpoints" / continuation.current_stage_id
        checkpoint_parent.mkdir(parents=True, exist_ok=True)
        checkpoint_target = checkpoint_parent / f"{kind}-{uuid4().hex[:12]}"
        report = StageSandboxCopier().copy_atomically(
            Path(snapshot.workspace_path),
            checkpoint_target,
            registered_root=artifact_root,
        )
        snapshot = StagePreparationResult(
            snapshot.workspace_alias,
            report.target,
            report.fingerprint,
            report.copied_files,
            True,
        )
        return self._checkpoint(
            session,
            continuation,
            snapshot,
            kind,
            f"snapshot:{continuation.current_stage_id}:{kind}",
            snapshot.fingerprint,
        )

    def persist_post_repair_checkpoint(
        self,
        session,
        continuation,
        snapshot: StagePreparationResult,
        *,
        attempt_id: str,
        proposal_artifact_id: str,
        proposal_checksum: str,
        apply_ledger_artifact_id: str,
        apply_ledger_checksum: str,
        post_fingerprint: str,
    ) -> StageCheckpointModel:
        if (
            snapshot.fingerprint != post_fingerprint
            or not proposal_artifact_id
            or not proposal_checksum
            or not apply_ledger_artifact_id
            or not apply_ledger_checksum
        ):
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Post-repair snapshot fingerprint does not match the Apply result",
            )
        binding = self._binding(session, continuation)
        if binding.workspace_fingerprint != post_fingerprint:
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Post-repair checkpoint is not bound to the active workspace fingerprint",
            )
        run = session.get(MigrationRunModel, continuation.run_id)
        if run is None:
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Post-repair checkpoint run binding is missing",
            )
        if not run.artifact_root:
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Post-repair checkpoint artifact root is missing",
            )
        # The active stage workspace is mutable and may be changed by the
        # next Angular-update retry. Persist an immutable copy before writing
        # the checkpoint manifest; pointing the checkpoint at the live
        # workspace makes later recovery read a different tree than the one
        # whose fingerprint was recorded.
        artifact_root = Path(run.artifact_root).resolve(strict=True)
        checkpoint_parent = artifact_root / "checkpoints" / continuation.current_stage_id
        checkpoint_parent.mkdir(parents=True, exist_ok=True)
        checkpoint_target = checkpoint_parent / f"post_repair-{attempt_id}-{uuid4().hex[:12]}"
        report = StageSandboxCopier().copy_atomically(
            Path(snapshot.workspace_path),
            checkpoint_target,
            registered_root=artifact_root,
        )
        snapshot = StagePreparationResult(
            snapshot.workspace_alias,
            report.target,
            report.fingerprint,
            report.copied_files,
            True,
        )
        payload = {
            "kind": "post_repair",
            "run_id": continuation.run_id,
            "stage_id": continuation.current_stage_id,
            "attempt_id": attempt_id,
            "proposal_artifact_id": proposal_artifact_id,
            "proposal_checksum": proposal_checksum,
            "apply_ledger_artifact_id": apply_ledger_artifact_id,
            "apply_ledger_checksum": apply_ledger_checksum,
            "post_fingerprint": post_fingerprint,
            "workspace_fingerprint": snapshot.fingerprint,
        }
        root = Path(run.artifact_root)
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        manifest = store.write_text_artifact(
            continuation.run_id,
            f"04_workflow_state/stages/{continuation.current_stage_id}/checkpoints/post-repair-{attempt_id}.json",
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=continuation.current_stage_id,
            attempt_id=attempt_id,
            created_by="transformer",
            created_at=self._now(),
            input_hashes={
                "proposal": proposal_checksum,
                "apply_ledger": apply_ledger_checksum,
                "post_fingerprint": post_fingerprint,
            },
            policy_version="transformer-post-repair-checkpoint-v1",
        )
        self.register_artifact(session, manifest, continuation)
        return self._checkpoint(
            session,
            continuation,
            snapshot,
            "post_repair",
            manifest.ref.artifact_id,
            manifest.ref.checksum,
            snapshot.fingerprint,
        )

    @staticmethod
    def reconstruct_workspace(
        snapshot_path: str,
        workspace_path: str,
        stage_root: str,
        expected_fingerprint: str,
        snapshot_root: str | None = None,
    ) -> str:
        snapshot = Path(snapshot_path).resolve(strict=False)
        workspace = Path(workspace_path).resolve(strict=False)
        root = Path(stage_root).resolve(strict=True)
        authorized_snapshot_roots = [root]
        if snapshot_root:
            authorized_snapshot_roots.append(Path(snapshot_root).resolve(strict=False))
        try:
            if not any(
                snapshot == candidate or candidate in snapshot.parents
                for candidate in authorized_snapshot_roots
            ):
                raise ValueError("snapshot is outside governed roots")
            workspace.relative_to(root)
        except ValueError as error:
            raise TransformerStageError(
                "WORKSPACE_RECONSTRUCTION_PATH_UNAUTHORIZED",
                "Checkpoint and workspace paths must remain within their governed roots",
            ) from error
        if snapshot == workspace:
            try:
                observed = StageSandboxCopier.fingerprint(workspace)
            except OSError as error:
                raise TransformerStageError(
                    "WORKSPACE_RECONSTRUCTION_EVIDENCE_MISSING",
                    "The lightweight checkpoint workspace is missing or unreadable",
                ) from error
            if observed != expected_fingerprint:
                raise TransformerStageError(
                    "WORKSPACE_RECONSTRUCTION_EVIDENCE_MISSING",
                    "The lightweight checkpoint cannot reproduce the expected state from the current workspace",
                )
            return observed
        snapshot = snapshot.resolve(strict=True)
        workspace = workspace.resolve(strict=True)
        if StageSandboxCopier.fingerprint(snapshot) != expected_fingerprint:
            raise TransformerStageError("CHECKPOINT_INTEGRITY_FAILED", "Checkpoint fingerprint changed")
        temporary = workspace.parent / f".{workspace.name}.reconstructing-{uuid4().hex[:12]}"
        quarantine = workspace.parent / f".{workspace.name}.interrupted-{uuid4().hex[:12]}"
        shutil.copytree(snapshot, temporary)
        try:
            workspace.replace(quarantine)
            temporary.replace(workspace)
        except Exception:
            if not workspace.exists() and quarantine.exists():
                quarantine.replace(workspace)
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        shutil.rmtree(quarantine)
        return StageSandboxCopier.fingerprint(workspace)

    def authoritative_checkpoint_fingerprint(
        self, session, checkpoint: StageCheckpointModel
    ) -> str | None:
        """The current-profile digest the checkpoint TREE must produce to be authoritative.

        A current-profile checkpoint anchors on its persisted hash: the tree
        must still reproduce it.  A legacy (pre-profile-identity) checkpoint
        stores a legacy-profile digest that is NOT comparable against live
        digests; its authoritative current digest is the one verified during
        legacy authority recovery (lineage row), so the tree must still
        reproduce that verified digest.  Returns None when the checkpoint is
        not authoritative (missing or tampered tree, or a legacy checkpoint
        without a verified recovery), and callers fail closed.
        """
        try:
            current = STAGE_FINGERPRINT_PROFILE.fingerprint(Path(checkpoint.workspace_path))
        except OSError:
            return None
        if current == checkpoint.workspace_fingerprint:
            return current
        try:
            legacy = LEGACY_STAGE_COMPLETE_FINGERPRINT_PROFILE.fingerprint(
                Path(checkpoint.workspace_path)
            )
        except OSError:
            return None
        if legacy == checkpoint.workspace_fingerprint:
            return current
        lineage = session.scalar(
            select(RepairFingerprintRecoveryModel).where(
                RepairFingerprintRecoveryModel.run_id == checkpoint.run_id,
                RepairFingerprintRecoveryModel.stage_id == checkpoint.stage_id,
                RepairFingerprintRecoveryModel.checkpoint_id == checkpoint.id,
            ).order_by(RepairFingerprintRecoveryModel.recovered_at.desc())
        )
        if lineage is None or lineage.current_fingerprint != current:
            return None
        return current

    def begin_reconstruction(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        checkpoint: StageCheckpointModel,
        reason: str,
        execution_id: str | None = None,
        attempt_id: str | None = None,
    ) -> None:
        """Record governed reconstruction intent before the filesystem swap.

        Verifies the durable binding still agrees with the immutable source
        checkpoint; on disagreement the reconstruction is refused and the
        FINGERPRINT_MISMATCH event is committed durably.  Otherwise the
        STARTED event is emitted in the caller's transaction (the tx that
        records intent).  The caller must then swap the workspace and write
        the ledger row + binding in one authoritative transaction.
        """
        transitions = StateTransitionService(session)
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if binding is not None and binding.workspace_fingerprint != checkpoint.workspace_fingerprint:
            authoritative = self.authoritative_checkpoint_fingerprint(session, checkpoint)
            if authoritative is None or binding.workspace_fingerprint != authoritative:
                transitions.append_audit_event(
                    run_id=continuation.run_id,
                    idempotency_key=(
                        f"{continuation.current_stage_id}:reconstruct:{reason}:{checkpoint.id}:mismatch"
                    ),
                    event_type=WorkflowEventType.STAGE_WORKSPACE_FINGERPRINT_MISMATCH,
                    actor="transformer",
                    reason="workspace binding fingerprint no longer matches the reconstruction checkpoint",
                    occurred_at=self._now(),
                    payload={
                        "stage_id": continuation.current_stage_id,
                        "checkpoint_id": checkpoint.id,
                        "binding_workspace_fingerprint": binding.workspace_fingerprint,
                        "checkpoint_workspace_fingerprint": checkpoint.workspace_fingerprint,
                        "reason": reason,
                    },
                )
                session.commit()
                raise TransformerStageError(
                    "WORKSPACE_FINGERPRINT_MISMATCH",
                    "Durable workspace binding no longer matches the reconstruction checkpoint",
                )
        transitions.append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=(
                f"{continuation.current_stage_id}:reconstruct:{reason}:{checkpoint.id}:started"
            ),
            event_type=WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED,
            actor="transformer",
            reason=f"workspace reconstruction started ({reason})",
            occurred_at=self._now(),
            payload={
                "stage_id": continuation.current_stage_id,
                "checkpoint_id": checkpoint.id,
                "checkpoint_fingerprint": checkpoint.workspace_fingerprint,
                "reason": reason,
                "execution_id": execution_id,
                "attempt_id": attempt_id,
            },
        )

    def record_reconstruction(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        checkpoint: StageCheckpointModel,
        reason: str,
        restored_fingerprint: str,
        execution_id: str | None = None,
        attempt_id: str | None = None,
    ) -> StageReconstructionRecordModel:
        """Write the durable ledger row and the RECONSTRUCTED event.

        Must be called in the same transaction as the authoritative binding /
        checkpoint state change so the binding is never updated while the
        ledger row is absent.
        """
        record = StageReconstructionRecordModel(
            id=f"reconstruction-{uuid4().hex[:12]}",
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            checkpoint_id=checkpoint.id,
            reason=reason,
            source_workspace_fingerprint=checkpoint.workspace_fingerprint,
            restored_workspace_fingerprint=restored_fingerprint,
            created_from_execution_id=execution_id,
            attempt_id=attempt_id,
            state_version=continuation.state_version,
            created_at=self._now(),
        )
        session.add(record)
        StateTransitionService(session).append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=f"{record.id}:reconstructed",
            event_type=WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTED,
            actor="transformer",
            reason=f"workspace reconstructed from immutable checkpoint ({reason})",
            occurred_at=self._now(),
            payload={
                "stage_id": continuation.current_stage_id,
                "checkpoint_id": checkpoint.id,
                "source_workspace_fingerprint": checkpoint.workspace_fingerprint,
                "restored_workspace_fingerprint": restored_fingerprint,
                "reason": reason,
                "execution_id": execution_id,
                "attempt_id": attempt_id,
                "ledger_record_id": record.id,
            },
        )
        session.flush()
        return record

    def _queue_group(
        self,
        session,
        continuation,
        *,
        group,
        next_node,
        attempt_key,
        checkpoint_id=None,
        prompt_id=None,
        recovery_of=None,
    ):
        run = session.get(MigrationRunModel, continuation.run_id)
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        binding = self._binding(session, continuation)
        preparation = StagePreparationResult(
            binding.alias,
            binding.workspace_path,
            binding.workspace_fingerprint,
            0,
            False,
        )
        request = SimpleNamespace(
            idempotency_key=(
                f"{continuation.id}:{continuation.current_stage_id}:command:{attempt_key}"
            )
        )
        try:
            result = self._stage_execution._authorize_and_queue_first_command(
                session,
                run,
                plan,
                stage_plan,
                preparation,
                request,
                run.actor or "transformer",
                group,
            )
        except StageExecutionError as error:
            raise TransformerStageError(error.code, error.message) from error
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == f"{group}-0",
            )
        )
        execution = session.get(CommandExecutionModel, result.execution_id)
        if recovery_of is not None:
            parent = session.get(CommandExecutionModel, recovery_of)
            if parent is None or execution.parent_execution_id not in (None, parent.id):
                raise TransformerStageError(
                    "TARGET_VERSION_RECOVERY_LINEAGE_INVALID",
                    "Target-version recovery execution is not bound to its failed parent",
                )
            execution.parent_execution_id = parent.id
            execution.attempt_number = (parent.attempt_number or 1) + 1
        execution.checkpoint_id = checkpoint_id
        execution.prompt_request_id = prompt_id
        if step is not None:
            step.execution_id = result.execution_id
            step.status = "RUNNING"
            step.updated_at = self._now()
        expected_state_version = continuation.state_version
        continuation.status = "waiting_command"
        continuation.current_node = next_node
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.waiting_execution_id = result.execution_id
        continuation.state_version += 1
        continuation.updated_at = self._now()
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
            key=f"wait:waiting_command:{expected_state_version}",
            reason="stage command queued; continuation waits for terminal evidence",
            payload={
                "execution_id": result.execution_id,
                "expected_state_version": expected_state_version,
            },
        )
        return result

    def _bootstrap_checkpoint(
        self,
        session,
        continuation: TransformationContinuationModel,
        execution: CommandExecutionModel,
    ) -> tuple[StageWorkspaceBindingModel, StageCheckpointModel, str, Path]:
        binding = self._binding(session, continuation)
        checkpoint_id = execution.checkpoint_id or binding.source_checkpoint_id
        checkpoint = session.get(StageCheckpointModel, checkpoint_id)
        if (
            checkpoint is None
            or checkpoint.run_id != continuation.run_id
            or checkpoint.stage_id != continuation.current_stage_id
            or checkpoint.kind != 'pre_bootstrap'
            or checkpoint.workspace_alias != binding.alias
            or not checkpoint.safe_for_resume
        ):
            raise TransformerStageError(
                'PRE_BOOTSTRAP_CHECKPOINT_MISSING',
                'The authoritative pre_bootstrap checkpoint is missing or invalid.',
            )
        if execution.checkpoint_id is not None and binding.source_checkpoint_id != checkpoint.id:
            raise TransformerStageError(
                'PRE_BOOTSTRAP_CHECKPOINT_MISSING',
                'Bootstrap execution and workspace binding reference different checkpoints.',
            )
        try:
            workspace = Path(binding.workspace_path).resolve(strict=True)
            checkpoint_path = Path(checkpoint.workspace_path).resolve(strict=True)
        except OSError as error:
            raise TransformerStageError(
                'PRE_BOOTSTRAP_CHECKPOINT_MISSING',
                'The authoritative pre_bootstrap workspace is unavailable.',
            ) from error
        if checkpoint_path != workspace:
            expected = self.authoritative_checkpoint_fingerprint(session, checkpoint)
            if expected is None:
                raise TransformerStageError(
                    'BOOTSTRAP_RECONSTRUCTION_FINGERPRINT_MISMATCH',
                    'The pre_bootstrap checkpoint fingerprint is not authoritative.',
                )
        else:
            # Legacy rows stored the active workspace as the checkpoint path.
            # The persisted checkpoint fingerprint remains the authority; a
            # baseline copy is validated against it only if reconstruction is
            # actually needed.
            expected = checkpoint.workspace_fingerprint
        return binding, checkpoint, expected, checkpoint_path

    def _legacy_bootstrap_source(
        self,
        session,
        continuation: TransformationContinuationModel,
        checkpoint: StageCheckpointModel,
    ) -> tuple[Path, Path]:
        run = session.get(MigrationRunModel, continuation.run_id)
        aliases = dict(run.workspace_aliases or {}) if run is not None else {}
        baseline = aliases.get('BASELINE_SANDBOX')
        stage_root = aliases.get('STAGE_SANDBOX')
        if not baseline or not stage_root:
            raise TransformerStageError(
                'PRE_BOOTSTRAP_CHECKPOINT_MISSING',
                'The legacy pre_bootstrap checkpoint has no safe reconstruction source.',
            )
        candidate = None
        try:
            stage_root_path = Path(stage_root).resolve(strict=True)
            candidate = stage_root_path / (
                f'.{continuation.current_stage_id}.bootstrap-source-{uuid4().hex[:12]}'
            )
            report = StageSandboxCopier().copy(
                Path(baseline), candidate, registered_root=stage_root_path
            )
        except Exception as error:
            if candidate is not None:
                shutil.rmtree(candidate, ignore_errors=True)
            raise TransformerStageError(
                'BOOTSTRAP_RECONSTRUCTION_FAILED',
                'The legacy pre_bootstrap workspace could not be reconstructed safely.',
            ) from error
        if report.fingerprint != checkpoint.workspace_fingerprint:
            shutil.rmtree(candidate, ignore_errors=True)
            raise TransformerStageError(
                'BOOTSTRAP_RECONSTRUCTION_FINGERPRINT_MISMATCH',
                'The safe reconstruction source does not match the pre_bootstrap checkpoint.',
            )
        return candidate, candidate

    def _bootstrap_recovery(
        self,
        session,
        continuation: TransformationContinuationModel,
        execution: CommandExecutionModel,
    ) -> None:
        binding, checkpoint, expected, checkpoint_path = self._bootstrap_checkpoint(
            session, continuation, execution
        )
        run = session.get(MigrationRunModel, continuation.run_id)
        if run is None:
            raise TransformerStageError(
                'BOOTSTRAP_RECONSTRUCTION_FAILED',
                'The migration run is unavailable for bootstrap recovery.',
            )
        workspace = Path(binding.workspace_path).resolve(strict=True)
        try:
            live = StageSandboxCopier.fingerprint(workspace)
        except OSError as error:
            raise TransformerStageError(
                'BOOTSTRAP_RECONSTRUCTION_FAILED',
                'The failed bootstrap workspace is unavailable for recovery.',
            ) from error
        if live != expected:
            source = checkpoint_path
            temporary_source = None
            if checkpoint_path == workspace:
                source, temporary_source = self._legacy_bootstrap_source(
                    session, continuation, checkpoint
                )
            try:
                self.begin_reconstruction(
                    session,
                    continuation,
                    checkpoint=checkpoint,
                    reason='bootstrap_retry_recovery',
                    execution_id=execution.id,
                )
            except TransformerStageError as error:
                if temporary_source is not None:
                    shutil.rmtree(temporary_source, ignore_errors=True)
                code = (
                    'BOOTSTRAP_RECONSTRUCTION_FINGERPRINT_MISMATCH'
                    if error.code == 'WORKSPACE_FINGERPRINT_MISMATCH'
                    else 'BOOTSTRAP_RECONSTRUCTION_FAILED'
                )
                raise TransformerStageError(
                    code,
                    'Bootstrap recovery could not establish reconstruction intent.',
                ) from error
            session.commit()
            try:
                restored = self.reconstruct_workspace(
                    str(source),
                    binding.workspace_path,
                    str(Path(binding.workspace_path).resolve().parent),
                    expected,
                    str(Path(run.artifact_root).resolve())
                    if temporary_source is None
                    else str(Path(binding.workspace_path).resolve().parent),
                )
            except TransformerStageError as error:
                code = (
                    'BOOTSTRAP_RECONSTRUCTION_FINGERPRINT_MISMATCH'
                    if error.code == 'CHECKPOINT_INTEGRITY_FAILED'
                    else 'BOOTSTRAP_RECONSTRUCTION_FAILED'
                )
                raise TransformerStageError(
                    code,
                    'Bootstrap recovery could not reconstruct the pre_bootstrap workspace.',
                ) from error
            except Exception as error:
                raise TransformerStageError(
                    'BOOTSTRAP_RECONSTRUCTION_FAILED',
                    'Bootstrap recovery could not reconstruct the pre_bootstrap workspace.',
                ) from error
            finally:
                if temporary_source is not None:
                    shutil.rmtree(temporary_source, ignore_errors=True)
            try:
                reconstructed_fingerprint = StageSandboxCopier.fingerprint(workspace)
            except OSError as error:
                raise TransformerStageError(
                    'BOOTSTRAP_RECONSTRUCTION_FINGERPRINT_MISMATCH',
                    'The reconstructed bootstrap workspace is unavailable for verification.',
                ) from error
            if restored != expected or reconstructed_fingerprint != expected:
                raise TransformerStageError(
                    'BOOTSTRAP_RECONSTRUCTION_FINGERPRINT_MISMATCH',
                    'Reconstructed bootstrap workspace does not match the pre_bootstrap checkpoint.',
                )
            self.record_reconstruction(
                session,
                continuation,
                checkpoint=checkpoint,
                reason='bootstrap_retry_recovery',
                restored_fingerprint=restored,
                execution_id=execution.id,
            )

        binding.workspace_fingerprint = expected
        binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
        binding.last_verified_fingerprint = expected
        binding.last_verified_at = self._now()
        session.flush()
        session.commit()

    def verify_bootstrap(self, session, continuation: TransformationContinuationModel) -> str:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "bootstrap_install-0",
            )
        )
        execution = session.get(CommandExecutionModel, step.execution_id) if step and step.execution_id else None
        if execution is not None and execution.status in {"pending", "queued", "running"}:
            self._wait_for_command(session, continuation, execution.id)
            return execution.id
        if (
            execution is not None
            and (
                execution.status == "failed"
                or (
                    execution.status == "interrupted"
                    and execution.reconstruction_required
                )
            )
        ):
            if execution.parent_execution_id is not None or (execution.attempt_number or 1) > 1:
                raise TransformerStageError(
                    execution.failure_code or 'BOOTSTRAP_INSTALL_FAILED',
                    execution.failure_message or 'Bootstrap retry failed.',
                )
            self._bootstrap_recovery(session, continuation, execution)
            try:
                retry = self._command_executor.queue_retry_execution(
                    session,
                    execution.id,
                    idempotency_key=f"{execution.id}:retry:1",
                    workspace_recovered=True,
                    authorized_timeout_seconds=self._planned_bootstrap_timeout(
                        session, continuation
                    ),
                )
            except CommandExecutorError as error:
                raise TransformerStageError(error.code, error.message) from error
            successor = session.get(CommandExecutionModel, retry.execution_id)
            step.execution_id = successor.id
            step.attempt_id = successor.id
            step.status = "RUNNING"
            step.updated_at = self._now()
            self._wait_for_command(session, continuation, successor.id)
            return successor.id
        if execution is None or execution.status != "succeeded":
            raise TransformerStageError(
                "BOOTSTRAP_INSTALL_FAILED",
                execution.failure_code if execution else "Bootstrap command evidence is missing",
            )
        binding = self._binding(session, continuation)
        workspace = Path(binding.workspace_path)
        fingerprint = self._stage_execution._preparation._copier.fingerprint(workspace)
        if fingerprint == binding.workspace_fingerprint and execution.command_id != "npm-ci-bootstrap":
            raise TransformerStageError("BOOTSTRAP_NO_CHANGE", "Bootstrap install produced no workspace change")
        binding.workspace_fingerprint = fingerprint
        binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
        binding.last_verified_fingerprint = fingerprint
        binding.last_verified_at = self._now()
        step.status = "PASSED"
        step.completed_at = self._now()
        step.workspace_fingerprint = fingerprint
        self._checkpoint(
            session,
            continuation,
            StagePreparationResult(binding.alias, binding.workspace_path, fingerprint, 0, False),
            "post_bootstrap",
            execution.result_artifact_id or execution.id,
            execution.runtime_checksum,
            execution.id,
        )
        continuation.status = "queued"
        continuation.current_node = "angular_update"
        continuation.last_error_code = None
        continuation.last_error_message = None
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = self._now()
        session.flush()
        return fingerprint

    def _planned_bootstrap_timeout(self, session, continuation) -> int:
        """Fresh validated timeout authority for the bootstrap retry.

        The bootstrap retry has no replacement authorization, so its timeout
        comes from the approved stage-plan reference the policy engine
        validated the original bootstrap command against.  Fail closed when
        the authority is absent.
        """
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        references = []
        if stage_plan is not None:
            references = (
                ((stage_plan.stage_plan or {}).get("commands") or {})
                .get("bootstrap_install")
                or []
            )
        planned = references[0] if len(references) == 1 else {}
        timeout = planned.get("timeout_seconds")
        if not isinstance(timeout, int) or timeout <= 0:
            raise TransformerStageError(
                "BOOTSTRAP_RETRY_TIMEOUT_MISSING",
                "The approved stage plan has no bootstrap install timeout authority",
            )
        return timeout

    def _wait_for_command(
        self,
        session,
        continuation: TransformationContinuationModel,
        execution_id: str,
    ) -> None:
        expected_state_version = continuation.state_version
        continuation.status = "waiting_command"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.waiting_execution_id = execution_id
        continuation.state_version += 1
        continuation.updated_at = self._now()
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
            key=f"wait:waiting_command:{expected_state_version}",
            reason="continuation waits for terminal command evidence",
            payload={
                "execution_id": execution_id,
                "expected_state_version": expected_state_version,
            },
        )

    @staticmethod
    def _request(run, continuation, gate):
        return SimpleNamespace(
            expected_state_version=run.state_version,
            idempotency_key=f"{continuation.id}:{continuation.current_stage_id}:prepare",
            artifact_set_checksum=gate.artifact_set_checksum,
            plan_checksum=continuation.plan_checksum,
            stage_plan_checksum=continuation.stage_plan_checksum,
            workspace_fingerprint=gate.workspace_fingerprint,
        )

    @staticmethod
    def _owned(session, continuation_id: str, worker_id: str):
        continuation = session.get(TransformationContinuationModel, continuation_id)
        if continuation is None or continuation.status != "running" or continuation.worker_id != worker_id:
            raise TransformerStageError("TRANSFORMATION_CLAIM_STALE", "Worker no longer owns continuation")
        return continuation

    @staticmethod
    def _binding(session, continuation):
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if binding is None:
            raise TransformerStageError("STAGE_WORKSPACE_MISSING", "Prepared stage workspace binding is missing")
        return binding

    def _checkpoint(
        self,
        session,
        continuation,
        preparation,
        kind,
        manifest_artifact_id,
        manifest_checksum,
        execution_id=None,
    ):
        for _attempt in range(2):
            latest = session.scalar(
                select(StageCheckpointModel)
                .where(StageCheckpointModel.stage_id == continuation.current_stage_id)
                .order_by(StageCheckpointModel.sequence.desc())
            )
            checkpoint = StageCheckpointModel(
                id=f"checkpoint-{uuid4().hex[:12]}",
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                kind=kind,
                sequence=(latest.sequence if latest else 0) + 1,
                source_checkpoint_id=latest.id if latest else None,
                workspace_alias=preparation.workspace_alias,
                workspace_path=preparation.workspace_path,
                workspace_fingerprint=preparation.fingerprint,
                manifest_artifact_id=manifest_artifact_id,
                manifest_checksum=manifest_checksum,
                created_from_execution_id=execution_id,
                safe_for_resume=True,
                sealed=False,
                state_version=continuation.state_version,
                created_at=self._now(),
            )
            try:
                with session.begin_nested():
                    session.add(checkpoint)
                    session.flush()
                return checkpoint
            except IntegrityError as error:
                detail = str(getattr(error, "orig", "") or error)
                if "stage_checkpoints" not in detail:
                    raise
        raise TransformerStageError(
            "CHECKPOINT_SEQUENCE_CONFLICT",
            "Concurrent checkpoint creation for the same stage exceeded the retry budget",
        )

    def _advance(self, continuation, node: str) -> None:
        continuation.current_node = node
        continuation.status = "queued"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = self._now()

    @staticmethod
    def checksum(value: object) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
