"""S1-F11-I02 durable baseline install application service."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.baseline_contracts import BaselineInstallRequest, BaselineInstallResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandLogWriter, CommandPolicy, ExecutionWorker
from app.domain.baseline_installation import (
    BaselineInstallPrerequisites,
    BaselineInstallationError,
    BaselineInstallationService,
    FrozenBaselineCommandPolicy,
)
from app.domain.contracts import ArtifactType, CommandStatus, WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    BaselineQualificationModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    MigrationRunModel,
)
from app.repositories.session import session_scope
from app.state.transition_service import StaleStateVersionError, StateTransitionService, TransitionRequest


class BaselineInstallApplicationError(ValueError):
    """Stable API-facing error from the baseline install application service."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class BaselineInstallApplicationService:
    """Persist and execute one idempotent, checksum-bound baseline install."""

    POLICY_VERSION = "baseline-install-v1"

    def __init__(self, *, session_scope_factory=session_scope, worker_factory=None, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._worker_factory = worker_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def install(self, run_id: str, request: BaselineInstallRequest) -> BaselineInstallResponse:
        queued_at = self._now()
        with self._scope() as session:
            run = self._run(session, run_id)
            existing = self._existing(session, run_id, request.idempotency_key)
            if existing is not None:
                if existing.runtime_profile_id != request.runtime_profile_id or existing.runtime_checksum != request.runtime_checksum or existing.timeout_seconds != request.timeout_seconds:
                    raise BaselineInstallApplicationError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different install request.", 409)
                return self._response(existing, idempotent_replay=True)
            baseline = self._baseline(session, run_id)
            if baseline is None:
                raise BaselineInstallApplicationError("BASELINE_WORKSPACE_REQUIRED", "Baseline qualification is required.", 409)
            if baseline.authorization_status != "authorized":
                raise BaselineInstallApplicationError("BASELINE_INSTALL_AUTHORIZATION_REQUIRED", "Baseline installation authorization is required.", 409)
            if baseline.blockers:
                raise BaselineInstallApplicationError("BASELINE_INSTALL_BLOCKED", "Blocked baseline prequalification cannot be installed.", 409)
            if run.state_version != request.expected_state_version:
                raise BaselineInstallApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)
            aliases = run.workspace_aliases or {}
            if not aliases.get("BASELINE_SANDBOX"):
                raise BaselineInstallApplicationError("BASELINE_LAYOUT_REQUIRED", "Registered baseline sandbox alias is required.", 409)
            profile = self._profile(session, run_id, request.runtime_profile_id, request.runtime_checksum)
            if profile is None:
                raise BaselineInstallApplicationError("EXECUTION_PROFILE_REQUIRED", "The selected execution profile checksum is required.", 409)
            lockfile = baseline.lockfile or {}
            if lockfile.get("status") not in {"valid", "qualified"}:
                raise BaselineInstallApplicationError("BASELINE_LOCKFILE_REQUIRED", "A valid lockfile is required before installation.", 409)

            command = FrozenBaselineCommandPolicy().create()
            queued = self._transition(session, run, request, WorkflowEventType.COMMAND_QUEUED, "baseline npm ci command queued", {"command_id": command.command_id})
            record = CommandExecutionModel(
                id=f"execution-{uuid4().hex[:12]}", run_id=run_id, stage_id=None,
                idempotency_key=request.idempotency_key, requested_by=request.actor, requester=request.actor,
                command_id=command.command_id, executable=command.executable, arguments=list(command.arguments),
                shell=False, working_directory_alias=command.working_directory_alias,
                runtime_profile_id=request.runtime_profile_id, runtime_checksum=request.runtime_checksum,
                baseline_checksum=baseline.checksum, timeout_seconds=request.timeout_seconds,
                network_profile=command.network_profile, cancellation_policy="terminate_process_tree",
                status=CommandStatus.PENDING.value, requested_at=queued_at, artifact_ids=[], blockers=[],
                state_version=queued.next_state_version, event_sequence=queued.event_sequence,
            )
            session.add(record)
            session.flush()
            execution_id = record.id
            sandbox = Path(aliases["BASELINE_SANDBOX"])

        with self._scope() as session:
            run = self._run(session, run_id)
            record = session.get(CommandExecutionModel, execution_id)
            if record is None:
                raise BaselineInstallApplicationError("COMMAND_EXECUTION_NOT_FOUND", "Command execution record disappeared.", 500)
            started = self._transition(session, run, request, WorkflowEventType.COMMAND_STARTED, "baseline npm ci command started", {"execution_id": execution_id}, expected_state_version=record.state_version)
            record.status = CommandStatus.RUNNING.value
            record.state_version = started.next_state_version
            record.event_sequence = started.event_sequence

        worker = self._worker(run, request.runtime_profile_id)
        command_request = FrozenBaselineCommandPolicy().create().request(
            run_id=run_id, runtime_profile_id=request.runtime_profile_id, timeout_seconds=request.timeout_seconds,
            idempotency_key=request.idempotency_key, actor=request.actor, requested_at=queued_at,
        )
        try:
            result = BaselineInstallationService(worker).execute(
                command_request, sandbox=sandbox,
                prerequisites=BaselineInstallPrerequisites(True, True, True, True, True),
            )
        except BaselineInstallationError as error:
            return self._finalize_failure(run_id, execution_id, request, error.code)
        except OSError:
            return self._finalize_failure(run_id, execution_id, request, "BASELINE_INSTALL_ENVIRONMENT_BLOCKED", environment_blocker="PROCESS_START_FAILED")
        except Exception:
            return self._finalize_failure(run_id, execution_id, request, "BASELINE_INSTALL_EXECUTION_FAILED")

        with self._scope() as session:
            run = self._run(session, run_id)
            record = session.get(CommandExecutionModel, execution_id)
            if record is None:
                raise BaselineInstallApplicationError("COMMAND_EXECUTION_NOT_FOUND", "Command execution record disappeared.", 500)
            artifacts = self._persist_artifacts(session, run, result, request, self._now())
            status = result.command.result.status
            record.status = status.value
            record.started_at = result.command.result.started_at
            record.finished_at = result.command.result.finished_at
            record.duration_ms = result.command.result.duration_ms
            record.exit_code = result.command.result.exit_code
            record.timed_out = result.command.timed_out
            record.cancelled = result.command.cancelled
            record.reconstruction_required = result.inspection.reconstruction_required
            record.start_fingerprint = {"package_json": asdict(result.inspection.package_json), "lockfile": asdict(result.inspection.lockfile)}
            record.end_fingerprint = record.start_fingerprint
            record.blockers = list(result.inspection.blockers)
            record.artifact_ids = artifacts
            record.command_log_artifact_id = result.command.command_log_artifact.ref.artifact_id
            record.stdout_artifact_id = result.command.stdout_artifact.ref.artifact_id if result.command.stdout_artifact else None
            record.stderr_artifact_id = result.command.stderr_artifact.ref.artifact_id if result.command.stderr_artifact else None
            expected_version = record.state_version
            if result.command.stdout_artifact or result.command.stderr_artifact:
                output = self._transition(session, run, request, WorkflowEventType.COMMAND_OUTPUT_AVAILABLE, "baseline npm ci output finalized", {"execution_id": record.id, "artifact_count": len(artifacts)}, expected_state_version=expected_version)
                expected_version = output.next_state_version
            event_type = WorkflowEventType.BASELINE_INSTALL_SUCCEEDED if status is CommandStatus.SUCCEEDED and not result.inspection.blockers else WorkflowEventType.COMMAND_INTERRUPTED if result.command.timed_out else WorkflowEventType.COMMAND_CANCELLED if result.command.cancelled else WorkflowEventType.BASELINE_INSTALL_FAILED
            completed = self._transition(session, run, request, event_type, "baseline npm ci command completed", {"execution_id": record.id, "status": record.status, "reconstruction_required": record.reconstruction_required}, expected_state_version=expected_version)
            record.state_version = completed.next_state_version
            record.event_sequence = completed.event_sequence
            session.flush()
            return self._response(record)

    def get(self, run_id: str, execution_id: str) -> BaselineInstallResponse | None:
        with self._scope() as session:
            record = session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id, CommandExecutionModel.id == execution_id))
            return self._response(record) if record is not None else None

    def _worker(self, run, runtime_profile_id: str) -> ExecutionWorker:
        if self._worker_factory is not None:
            return self._worker_factory(run)
        baseline = Path((run.workspace_aliases or {})["BASELINE_SANDBOX"]).resolve()
        root = Path(run.artifact_root).resolve()
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        policy = CommandPolicy(sandbox_root=baseline, working_directory_aliases={"BASELINE_SANDBOX": baseline}, runtime_profiles=frozenset({runtime_profile_id}), network_profiles=frozenset({"approved-registries-only"}))
        return ExecutionWorker(policy, CommandLogWriter(store))

    @staticmethod
    def _run(session, run_id: str) -> MigrationRunModel:
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise BaselineInstallApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        return run

    @staticmethod
    def _baseline(session, run_id: str) -> BaselineQualificationModel | None:
        return session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == run_id).order_by(BaselineQualificationModel.created_at.desc()))

    @staticmethod
    def _profile(session, run_id: str, profile_id: str, checksum: str) -> ExecutionProfileModel | None:
        record = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.created_at.desc()))
        if record is None or record.selected_profile_id != profile_id or record.selected_checksum != checksum:
            return None
        return record

    @staticmethod
    def _existing(session, run_id: str, key: str) -> CommandExecutionModel | None:
        return session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id, CommandExecutionModel.idempotency_key == key))

    def _transition(self, session, run, request, event_type, reason, payload, *, expected_state_version=None):
        try:
            return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=run.state_version if expected_state_version is None else expected_state_version, idempotency_key=request.idempotency_key + ":" + event_type.value, event_type=event_type, actor=request.actor, reason=reason, occurred_at=self._now(), payload=payload))
        except StaleStateVersionError as error:
            raise BaselineInstallApplicationError("STALE_STATE_VERSION", str(error), 409) from error

    def _finalize_failure(self, run_id: str, execution_id: str, request: BaselineInstallRequest, blocker: str, *, environment_blocker: str | None = None) -> BaselineInstallResponse:
        with self._scope() as session:
            run = self._run(session, run_id)
            record = session.get(CommandExecutionModel, execution_id)
            if record is None:
                raise BaselineInstallApplicationError("COMMAND_EXECUTION_NOT_FOUND", "Command execution record disappeared.", 500)
            record.status = CommandStatus.FAILED.value
            record.finished_at = self._now()
            record.blockers = [blocker]
            record.environment_blocker = environment_blocker
            completed = self._transition(session, run, request, WorkflowEventType.BASELINE_INSTALL_FAILED, "baseline npm ci command failed before completion", {"execution_id": execution_id, "blocker": blocker}, expected_state_version=record.state_version)
            record.state_version = completed.next_state_version
            record.event_sequence = completed.event_sequence
            session.flush()
            return self._response(record)
    def _persist_artifacts(self, session, run, result, request, now: datetime) -> list[str]:
        root = Path(run.artifact_root).resolve()
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        artifacts = [result.command.command_log_artifact]
        if result.command.stdout_artifact:
            artifacts.append(result.command.stdout_artifact)
        if result.command.stderr_artifact:
            artifacts.append(result.command.stderr_artifact)
        payloads = {
            "01_baseline/npm-ci-command.json": {"command_id": "npm-ci-bootstrap", "executable": "npm", "arguments": ["ci"], "shell": False, "working_directory_alias": "BASELINE_SANDBOX", "runtime_profile_id": request.runtime_profile_id, "runtime_checksum": request.runtime_checksum},
            "01_baseline/dependency_tree_verification.json": asdict(result.inspection.dependency_tree) if result.inspection.dependency_tree else {"status": "not_run"},
            "01_baseline/lockfile_post_install_verification.json": {"package_json": asdict(result.inspection.package_json), "lockfile": asdict(result.inspection.lockfile), "unchanged": not result.inspection.blockers},
            "01_baseline/baseline_install_summary.json": {"status": result.inspection.status, "blockers": list(result.inspection.blockers), "reconstruction_required": result.inspection.reconstruction_required},
        }
        for relative_path, payload in payloads.items():
            stored = store.write_text_artifact(run.id, relative_path, json.dumps(payload, indent=2, sort_keys=True, default=str), ArtifactType.JSON, created_by="baseline-install-application-service", created_at=now, input_hashes={"request": request.idempotency_key, "baseline": request.runtime_checksum}, policy_version=self.POLICY_VERSION)
            artifacts.append(stored)
        ids = []
        for artifact in artifacts:
            session.add(ArtifactMetadataModel(id=f"metadata-{artifact.ref.artifact_id}", run_id=run.id, stage_id=None, artifact_type=artifact.ref.artifact_type.value, relative_path=artifact.ref.relative_path, checksum=artifact.ref.checksum, created_at=artifact.ref.created_at))
            ids.append(artifact.ref.artifact_id)
        return ids

    @staticmethod
    def _response(record, *, idempotent_replay=False) -> BaselineInstallResponse:
        return BaselineInstallResponse(run_id=record.run_id, execution_id=record.id, command_id=record.command_id, status=record.status, exit_code=record.exit_code, started_at=record.started_at.isoformat() if record.started_at else None, finished_at=record.finished_at.isoformat() if record.finished_at else None, duration_ms=record.duration_ms, timed_out=record.timed_out, cancelled=record.cancelled, reconstruction_required=record.reconstruction_required, runtime_checksum=record.runtime_checksum, baseline_checksum=record.baseline_checksum, start_fingerprint=record.start_fingerprint, end_fingerprint=record.end_fingerprint, blockers=record.blockers or [], artifact_ids=record.artifact_ids or [], state_version=record.state_version, event_sequence=record.event_sequence, idempotent_replay=idempotent_replay)
