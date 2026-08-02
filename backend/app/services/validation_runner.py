"""Shared durable command runner for Transformer install, build, and test checks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationPlanModel,
    MigrationRunModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.services.stage_execution_application_service import (
    StageExecutionApplicationService,
    StageExecutionError,
)
from app.services.stage_preparation_application_service import StagePreparationResult
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformation_continuation_service import (
    append_continuation_event,
)
from app.services.workspace_fingerprint import SOURCE_CONFIG_FINGERPRINT_PROFILE


class ValidationRunnerError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ValidationRunner:
    terminal = {"succeeded", "failed", "timed_out", "cancelled", "interrupted"}

    def __init__(self, *, stage_execution=None, now_provider=None) -> None:
        self._stage_execution = stage_execution or StageExecutionApplicationService()
        self._now = now_provider or (lambda: datetime.now(UTC))

    def advance_group(
        self,
        session,
        continuation: TransformationContinuationModel,
        group: str,
        *,
        next_node: str,
        attempt_key: str = "initial",
    ) -> str:
        run, plan, stage_plan, binding, references = self._context(session, continuation, group)
        for index, _reference in enumerate(references):
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == f"{group}-{index}",
                )
            )
            if step is None:
                raise ValidationRunnerError("VALIDATION_STEP_MISSING", f"{group}-{index} is missing")
            execution = (
                session.get(CommandExecutionModel, step.execution_id) if step.execution_id else None
            )
            if execution is None:
                fingerprint = self.source_fingerprint(Path(binding.workspace_path))
                request = SimpleNamespace(
                    idempotency_key=f"{continuation.id}:validation:{attempt_key}:{group}"
                )
                try:
                    queued = self._stage_execution._authorize_and_queue_first_command(
                        session,
                        run,
                        plan,
                        stage_plan,
                        StagePreparationResult(
                            binding.alias, binding.workspace_path, binding.workspace_fingerprint, 0, False
                        ),
                        request,
                        run.actor or "transformer",
                        group,
                        command_index=index,
                    )
                except StageExecutionError as error:
                    raise ValidationRunnerError(error.code, error.message) from error
                execution = session.get(CommandExecutionModel, queued.execution_id)
                execution.start_fingerprint = {"source_config": fingerprint}
                step.execution_id = execution.id
                step.status = "RUNNING"
                step.started_at = self._now()
                step.updated_at = self._now()
                self._wait(session, continuation, next_node=continuation.current_node, execution_id=execution.id)
                return "queued"
            if execution.status not in self.terminal:
                self._wait(session, continuation, next_node=continuation.current_node, execution_id=execution.id)
                return "waiting"
            if execution.status != "succeeded" or execution.exit_code != 0:
                step.status = "FAILED"
                step.completed_at = self._now()
                expected_state_version = continuation.state_version
                failure_code = execution.failure_code or "VALIDATION_COMMAND_FAILED"
                continuation.status = "queued"
                continuation.current_node = "classify_failure"
                continuation.last_error_code = failure_code
                continuation.last_error_message = execution.failure_message or f"{group}-{index} failed"
                continuation.state_version += 1
                continuation.updated_at = self._now()
                session.flush()
                append_continuation_event(
                    session,
                    continuation,
                    event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_FAILED,
                    key=f"failed:{expected_state_version}:{failure_code}",
                    reason="validation command failed; failure classification queued",
                    payload={
                        "last_error_code": failure_code,
                        "execution_id": execution.id,
                        "expected_state_version": expected_state_version,
                    },
                )
                return "failed"
            if not execution.command_log_artifact_id or not execution.result_artifact_id:
                raise ValidationRunnerError(
                    "VALIDATION_EVIDENCE_MISSING",
                    f"{group}-{index} returned zero without finalized command evidence",
                )
            observed = self.source_fingerprint(Path(binding.workspace_path))
            expected = (execution.start_fingerprint or {}).get("source_config")
            execution.end_fingerprint = {"source_config": observed}
            if expected != observed:
                raise ValidationRunnerError(
                    "VALIDATION_WORKSPACE_MUTATED",
                    f"{group}-{index} unexpectedly changed source or configuration files",
                )
            step.status = "PASSED"
            step.completed_at = self._now()
            step.workspace_fingerprint = observed
            step.output_checksum = execution.runtime_checksum
            step.artifact_ids = list(execution.artifact_ids or [])
            step.updated_at = self._now()
            binding.workspace_fingerprint = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
            binding.last_verified_fingerprint = binding.workspace_fingerprint
            binding.last_verified_at = self._now()
        continuation.status = "queued"
        continuation.current_node = next_node
        continuation.state_version += 1
        continuation.updated_at = self._now()
        return "passed"

    def aggregate(self, session, continuation: TransformationContinuationModel):
        run = session.get(MigrationRunModel, continuation.run_id)
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        binding = self._binding(session, continuation)
        value = stage_plan.stage_plan or {}
        policy = value.get("validation_policy") or {}
        required = ["final_install", *self.required_groups(policy)]
        checks = []
        for group in required:
            references = (value.get("commands") or {}).get(group) or []
            if not references:
                raise ValidationRunnerError(
                    "VALIDATION_TARGET_MISSING", f"Approved validation target {group} is missing"
                )
            for index in range(len(references)):
                step = session.scalar(
                    select(StageStepModel).where(
                        StageStepModel.stage_id == continuation.current_stage_id,
                        StageStepModel.name == f"{group}-{index}",
                    )
                )
                if step is None or step.status != "PASSED" or not step.execution_id:
                    raise ValidationRunnerError(
                        "VALIDATION_INCOMPLETE", f"{group}-{index} has no current passing evidence"
                    )
                execution = session.get(CommandExecutionModel, step.execution_id)
                if not execution or not execution.command_log_artifact_id or not execution.result_artifact_id:
                    raise ValidationRunnerError(
                        "VALIDATION_EVIDENCE_MISSING", f"{group}-{index} evidence is incomplete"
                    )
                checks.append(
                    {
                        "group": group,
                        "index": index,
                        "execution_id": execution.id,
                        "runtime_checksum": execution.runtime_checksum,
                        "artifact_ids": list(execution.artifact_ids or []),
                    }
                )
        fingerprint = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
        if fingerprint != binding.workspace_fingerprint:
            raise ValidationRunnerError(
                "VALIDATION_BINDING_STALE", "Validation workspace no longer matches its binding"
            )
        payload = {
            "schema_version": "transformer-validation-v1",
            "run_id": continuation.run_id,
            "stage_id": continuation.current_stage_id,
            "stage_plan_checksum": continuation.stage_plan_checksum,
            "workspace_fingerprint": fingerprint,
            "required_groups": required,
            "checks": checks,
            "status": "passed",
        }
        return payload, run.artifact_root

    def write_summary(self, payload: dict[str, object], artifact_root: str):
        root = Path(artifact_root)
        return LocalFilesystemArtifactStore(root.parent, fixed_run_root=root).write_text_artifact(
            str(payload["run_id"]),
            f"04_workflow_state/stages/{payload['stage_id']}/validation/summary.json",
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=str(payload["stage_id"]),
            created_by="validation-runner",
            created_at=self._now(),
            input_hashes={"stage_plan": str(payload["stage_plan_checksum"])},
            policy_version="transformer-validation-v1",
        )

    @staticmethod
    def register_summary(session, continuation, stored) -> None:
        if session.get(ArtifactMetadataModel, "metadata-" + stored.ref.artifact_id) is None:
            session.add(
                ArtifactMetadataModel(
                    id="metadata-" + stored.ref.artifact_id,
                    run_id=continuation.run_id,
                    stage_id=continuation.current_stage_id,
                    artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path,
                    checksum=stored.ref.checksum,
                    created_at=stored.ref.created_at,
                    finalized_at=stored.ref.created_at,
                    immutable=True,
                )
            )

    @staticmethod
    def required_groups(policy: dict[str, object]) -> list[str]:
        mapping = {"build": "builds", "test": "tests", "lint": "lint"}
        checks = policy.get("required_checks") or ("build", "test")
        groups = []
        for check in checks:
            if check not in mapping:
                raise ValidationRunnerError(
                    "VALIDATION_CHECK_UNSUPPORTED", f"Unsupported required check: {check}"
                )
            if mapping[check] not in groups:
                groups.append(mapping[check])
        return groups

    @staticmethod
    def source_fingerprint(root: Path) -> str:
        """Fingerprint source and configuration files, excluding generated outputs.

        Delegates to the canonical source-config workspace fingerprint profile.
        """
        return SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(root)

    def _wait(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        next_node: str,
        execution_id: str,
    ) -> None:
        expected_state_version = continuation.state_version
        continuation.status = "waiting_command"
        continuation.current_node = next_node
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
            reason="validation command queued; continuation waits for terminal evidence",
            payload={
                "execution_id": execution_id,
                "expected_state_version": expected_state_version,
            },
        )

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
            raise ValidationRunnerError("STAGE_WORKSPACE_MISSING", "Stage workspace is missing")
        return binding

    def _context(self, session, continuation, group):
        run = session.get(MigrationRunModel, continuation.run_id)
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        binding = self._binding(session, continuation)
        references = ((stage_plan.stage_plan or {}).get("commands") or {}).get(group) or []
        if not references:
            raise ValidationRunnerError(
                "VALIDATION_TARGET_MISSING", f"Approved validation target {group} is missing"
            )
        return run, plan, stage_plan, binding, references


class BuildAgent:
    def __init__(self, runner: ValidationRunner | None = None) -> None:
        self.runner = runner or ValidationRunner()

    def advance(
        self, session, continuation, *, next_node: str, attempt_key: str = "initial"
    ) -> str:
        return self.runner.advance_group(
            session, continuation, "builds", next_node=next_node, attempt_key=attempt_key
        )


class TestAgent:
    def __init__(self, runner: ValidationRunner | None = None) -> None:
        self.runner = runner or ValidationRunner()

    def advance(
        self,
        session,
        continuation,
        group: str,
        *,
        next_node: str,
        attempt_key: str = "initial",
    ) -> str:
        return self.runner.advance_group(
            session, continuation, group, next_node=next_node, attempt_key=attempt_key
        )
