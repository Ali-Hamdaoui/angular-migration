"""CommandExecutor application service for G01 S3-F02.

CommandExecutor wraps the Sprint 0 ExecutionWorker with proper
authorization, persistence, event emission, and artifact registration.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import shutil
import threading
import queue
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import uuid4
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.command_execution.worker import (
    CommandDefinition,
    CommandPolicy,
    CommandPolicyViolation,
    CommandRegistry,
    CommandLogWriter,
    ExecutionWorker,
    WorkerSupervisor,
    StructuredCommandRequest,
    SupervisedProcessResult,
)
from app.domain.contracts import (
    ArtifactRefDto,
    ArtifactType,
    CommandRequestDto,
    CommandResultDto,
    CommandStatus,
    CancellationPolicy,
    WorkflowEventType,
    CommandPolicyValidateRequestDto,
    CommandPolicyValidateResponseDto,
    RunStatus,
)
from app.repositories.models.workflow import (
    ArtifactMetadataModel,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    MigrationRunModel,
    WorkflowEventModel,
)
from app.repositories.models import ExecutionProfileModel
from app.artifact_store import LocalFilesystemArtifactStore
from app.services.command_registry_service import (
    CommandPolicyEngineService,
    CommandRegistryService,
)
from app.domain.command import command_arguments_match
from app.services.job_supervisor_service import JobSupervisorService
from app.services.command_log_service import CommandLogService


class CommandExecutorError(ValueError):
    """Raised when a command execution operation fails."""
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


_WORKER_MUTABLE_WORKSPACE_ALIASES = frozenset({
    "run_workspace",
    "BASELINE_SANDBOX",
    "STAGE_SANDBOX",
    "REPAIR_SANDBOX",
    "FINAL_ASSURANCE_SANDBOX",
    "DELIVERY_CANDIDATE",
})


def worker_workspace_aliases(aliases: Mapping[str, str | Path], authorized_alias: str | None) -> dict[str, Path]:
    """Expose exactly one approved mutable workspace to the worker."""
    if not authorized_alias:
        raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The authorized command has no bound workspace alias.")
    path = aliases.get(authorized_alias)
    if path is None:
        raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The authorized workspace alias is not bound for this run.")
    try:
        resolved_path = Path(path).resolve(strict=True)
    except FileNotFoundError as error:
        raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The authorized workspace alias is not available.") from error
    if not resolved_path.is_dir():
        raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The authorized workspace alias is not a directory.")
    if re.fullmatch(r"STAGE_WORKSPACE_[A-Z0-9_]+", authorized_alias):
        stage_root = aliases.get("STAGE_SANDBOX")
        if stage_root is None:
            raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The authorized stage workspace alias has no stage sandbox root.")
        try:
            resolved_root = Path(stage_root).resolve(strict=True)
        except FileNotFoundError as error:
            raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The stage sandbox root is not available.") from error
        if resolved_path == resolved_root or not resolved_path.is_relative_to(resolved_root):
            raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The authorized stage workspace alias is outside the bound stage sandbox.")
    elif authorized_alias not in _WORKER_MUTABLE_WORKSPACE_ALIASES:
        raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The authorized workspace alias is not mutable.")
    return {authorized_alias: resolved_path}


@dataclass(frozen=True)
class CommandExecutionResponse:
    """Result from the command executor service."""
    execution_id: str
    run_id: str
    command_id: str
    status: str
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
    artifacts: tuple[ArtifactRefDto, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    stage_id: str | None = None
    authorization_id: str | None = None
    template_id: str | None = None
    template_version: int | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    execution_profile_id: str | None = None
    workspace_alias: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    exit_code: int | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    correlation_id: str | None = None
    request_payload_hash: str | None = None
    stdout_artifact_id: str | None = None
    stderr_artifact_id: str | None = None
    command_log_artifact_id: str | None = None
    manifest_artifact_id: str | None = None
    result_artifact_id: str | None = None
    executable: str | None = None
    arguments: list[str] = field(default_factory=list)
    safe_relative_working_directory: str | None = None
    runtime_checksum: str | None = None
    worker_id: str | None = None
    cancel_requested_at: datetime | None = None
    cancel_requested_by: str | None = None
    cancelled: bool = False
    timed_out: bool = False


class CommandExecutorService:
    """Authoritative command execution service.

    Orchestrates: authorization → queuing → process launch → output capture
    → artifact persistence → event emission.
    """

    def __init__(
        self,
        policy_engine: CommandPolicyEngineService | None = None,
        registry_service: CommandRegistryService | None = None,
        supervisor: WorkerSupervisor | None = None,
        default_timeout_seconds: int = 300,
    ) -> None:
        self._policy_engine = policy_engine or CommandPolicyEngineService()
        self._registry_service = registry_service or CommandRegistryService()
        self._supervisor = supervisor or WorkerSupervisor()
        self._default_timeout_seconds = default_timeout_seconds
        self._job_supervisor = JobSupervisorService()
        # Retained for the disabled legacy path; authoritative execution uses
        # JobSupervisorService's process-owned registry above.
        self._cancel_events: dict[str, threading.Event] = {}

    # The executor is process-owned, not request-owned.  This is deliberately
    # a small MVP worker pool; the durable execution row is the queue and the
    # worker always opens its own database session.
    _worker_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="amfa-command")
    _dispatch_lock = threading.Lock()
    _dispatched_execution_ids: set[str] = set()

    _LEGAL_EXECUTION_TRANSITIONS = {
        CommandStatus.PENDING.value: {CommandStatus.QUEUED.value, CommandStatus.FAILED.value},
        CommandStatus.QUEUED.value: {CommandStatus.RUNNING.value, CommandStatus.FAILED.value},
        CommandStatus.RUNNING.value: {
            CommandStatus.SUCCEEDED.value, CommandStatus.FAILED.value,
            CommandStatus.TIMED_OUT.value, CommandStatus.CANCELLED.value,
        },
        CommandStatus.SUCCEEDED.value: set(),
        CommandStatus.FAILED.value: set(),
        CommandStatus.TIMED_OUT.value: set(),
        CommandStatus.CANCELLED.value: set(),
    }

    @classmethod
    def transition_execution(cls, session: Session, model: CommandExecutionModel, next_status: str, *, now: datetime | None = None) -> None:
        """Apply the command-execution aggregate's legal transition table.

        Command executions are a separate aggregate from migration-run state:
        the worker owns this row after dispatch, while the run remains owned by
        the run Transition Service. This boundary validates terminal immutability
        and versions every execution mutation before its event is appended.
        """
        current = model.status
        if next_status == current:
            return
        if next_status not in cls._LEGAL_EXECUTION_TRANSITIONS.get(current, set()):
            raise CommandExecutorError("ILLEGAL_EXECUTION_TRANSITION", f"Cannot move execution from {current} to {next_status}")
        occurred_at = now or datetime.now(UTC)
        model.status = next_status
        model.state_version = (model.state_version or 1) + 1
        if next_status == CommandStatus.RUNNING.value:
            model.started_at = occurred_at
        if next_status in {CommandStatus.SUCCEEDED.value, CommandStatus.FAILED.value, CommandStatus.TIMED_OUT.value, CommandStatus.CANCELLED.value}:
            model.finished_at = occurred_at
        session.flush()

    def queue_authorized_command(
        self,
        session: Session,
        *,
        run_id: str,
        authorization_decision_id: str,
        expected_state_version: int,
        idempotency_key: str,
        requested_by: str | None = None,
        correlation_id: str | None = None,
    ) -> CommandExecutionResponse:
        """Persist one execution from an accepted, immutable authorization.

        No command data is accepted from the caller.  The authorization audit,
        run, template, and profile are the only sources for execution inputs.
        Dispatch happens after the surrounding transaction commits.
        """
        existing = session.scalar(select(CommandExecutionModel).where(
            CommandExecutionModel.run_id == run_id,
            CommandExecutionModel.idempotency_key == idempotency_key,
        ))
        if existing is not None:
            if (existing.authorization_id != authorization_decision_id
                    or existing.authoritative_state_version != expected_state_version):
                raise CommandExecutorError("IDEMPOTENCY_KEY_REUSED", "Idempotency key is bound to a different request")
            return self._response_from_model(existing, idempotent_replay=True)

        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise CommandExecutorError("RUN_NOT_FOUND", "Migration run does not exist")
        if run.state_version != expected_state_version:
            raise CommandExecutorError(
                "STALE_STATE_VERSION", "The run state version is stale",
                {"requested_version": expected_state_version, "current_version": run.state_version, "run_id": run_id},
            )

        authorization = session.get(CommandAuthorizationAuditModel, authorization_decision_id)
        if authorization is None:
            raise CommandExecutorError("AUTHORIZATION_DECISION_NOT_FOUND", "Authorization decision does not exist")
        if authorization.run_id != run_id:
            raise CommandExecutorError("AUTHORIZATION_RUN_MISMATCH", "Authorization belongs to another run")
        if authorization.decision != "accepted":
            raise CommandExecutorError("AUTHORIZATION_DECISION_REJECTED", "Only an accepted authorization may execute")
        if authorization.expected_state_version != expected_state_version or authorization.state_version != run.state_version:
            raise CommandExecutorError("AUTHORIZATION_STALE", "Authorization is stale for the current run state")
        if authorization.idempotency_key != idempotency_key:
            raise CommandExecutorError("AUTHORIZATION_IDEMPOTENCY_MISMATCH", "Execution key does not match authorization")
        if authorization.stage_id and not self._stage_belongs_to_run(session, authorization.stage_id, run_id):
            raise CommandExecutorError("AUTHORIZATION_STAGE_MISMATCH", "Authorization stage does not belong to the run")

        template = self._registry_service.find_registered_template(
            session,
            template_id=authorization.template_id or "",
            command_id=authorization.command_id,
            version=authorization.template_version or 0,
        )
        if template is None:
            raise CommandExecutorError("COMMAND_TEMPLATE_NOT_FOUND", "The authorized command template is unavailable")
        if template.executable not in {authorization.executable, *(template.executable_aliases or [])}:
            raise CommandExecutorError("AUTHORIZATION_STALE", "Authorized executable no longer matches the template")
        if not command_arguments_match(tuple(template.arguments), tuple(authorization.arguments or [])):
            raise CommandExecutorError("AUTHORIZATION_STALE", "Authorized arguments no longer match the template")
        if not authorization.execution_profile_id:
            raise CommandExecutorError("EXECUTION_PROFILE_NOT_FOUND", "Authorization has no execution profile")
        profile = session.scalar(select(ExecutionProfileModel).where(
            ExecutionProfileModel.run_id == run_id,
            ExecutionProfileModel.selected_profile_id == authorization.execution_profile_id,
        ).order_by(ExecutionProfileModel.created_at.desc()))
        if profile is None or profile.status not in {"resolved", "selected"}:
            raise CommandExecutorError("EXECUTION_PROFILE_NOT_APPROVED", "Execution profile is not approved for this run")
        if not run.run_root or not run.artifact_root or not run.workspace_aliases:
            raise CommandExecutorError("WORKSPACE_NOT_AVAILABLE", "Run-owned workspace configuration is unavailable")
        if authorization.stage_id and (authorization.workspace_alias or "").startswith("STAGE_WORKSPACE_"):
            from app.repositories.models import StageWorkspaceBindingModel

            binding = session.scalar(select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == run_id,
                StageWorkspaceBindingModel.stage_id == authorization.stage_id,
                StageWorkspaceBindingModel.alias == authorization.workspace_alias,
                StageWorkspaceBindingModel.active.is_(True),
            ))
            if binding is None or (run.workspace_aliases or {}).get(authorization.workspace_alias) != binding.workspace_path:
                raise CommandExecutorError("WORKSPACE_ALIAS_NOT_BOUND", "The authorized stage workspace alias has no matching durable binding")

        now = datetime.now(UTC)
        normalized_payload = {
            "run_id": run_id, "authorization_decision_id": authorization.id,
            "expected_state_version": expected_state_version, "stage_id": authorization.stage_id,
            "template_id": authorization.template_id, "template_version": authorization.template_version,
            "plan_id": authorization.plan_id, "plan_version": authorization.plan_version,
            "command_id": authorization.command_id, "executable": authorization.executable,
            "arguments": list(authorization.arguments or []),
            "execution_profile_id": authorization.execution_profile_id,
            "workspace_alias": authorization.workspace_alias,
            "network_profile": authorization.network_profile or "none",
        }
        payload_hash = "sha256:" + hashlib.sha256(
            json.dumps(normalized_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        execution_id = f"exec-{uuid4().hex[:12]}"
        model = CommandExecutionModel(
            id=execution_id,
            run_id=run_id,
            stage_id=authorization.stage_id,
            authorization_id=authorization.id,
            template_id=authorization.template_id,
            template_version=authorization.template_version,
            plan_id=authorization.plan_id,
            plan_version=authorization.plan_version,
            idempotency_key=idempotency_key,
            request_payload_hash=payload_hash,
            correlation_id=correlation_id or authorization.correlation_id,
            authoritative_state_version=run.state_version,
            requested_by=requested_by or authorization.actor,
            executable=authorization.executable,
            arguments=list(authorization.arguments or []),
            working_directory_alias=authorization.workspace_alias,
            safe_relative_working_directory=authorization.workspace_alias,
            runtime_profile_id=authorization.execution_profile_id,
            status=CommandStatus.QUEUED.value,
            command_id=authorization.command_id,
            shell=False,
            timeout_seconds=300,
            network_profile=authorization.network_profile or "none",
            cancellation_policy="terminate_process_tree",
            requested_at=now,
            state_version=1,
            event_sequence=1,
            worker_id=None,
        )
        session.add(model)
        session.flush()
        self._append_event(session, run_id, authorization.stage_id, f"{idempotency_key}:queued",
                           WorkflowEventType.COMMAND_QUEUED, "authorized command queued",
                           {"execution_id": execution_id, "authorization_id": authorization.id,
                            "command_id": authorization.command_id, "state_version": run.state_version})
        return self._response_from_model(model)

    def dispatch_execution(self, execution_id: str) -> None:
        """Transfer a committed execution to the process-owned worker."""
        with self._dispatch_lock:
            if execution_id in self._dispatched_execution_ids:
                return
            self._dispatched_execution_ids.add(execution_id)
        from app.repositories.session import session_scope
        dispatch_owner = f"dispatch-{uuid4().hex[:12]}"
        with session_scope() as session:
            claimed = session.execute(update(CommandExecutionModel).where(
                CommandExecutionModel.id == execution_id,
                CommandExecutionModel.status == CommandStatus.QUEUED.value,
                CommandExecutionModel.worker_id.is_(None),
            ).values(worker_id=dispatch_owner)).rowcount
        if claimed != 1:
            return
        try:
            self._worker_pool.submit(self._run_execution, execution_id)
        except Exception:
            with self._dispatch_lock:
                self._dispatched_execution_ids.discard(execution_id)
            with session_scope() as session:
                session.execute(update(CommandExecutionModel).where(
                    CommandExecutionModel.id == execution_id,
                    CommandExecutionModel.worker_id == dispatch_owner,
                ).values(worker_id=None))
            raise

    def _run_execution(self, execution_id: str) -> None:
        from app.repositories.session import session_scope
        worker_id = threading.current_thread().name
        with session_scope() as session:
            model = session.get(CommandExecutionModel, execution_id)
            if model is None or model.status != CommandStatus.QUEUED.value:
                return
            run = session.get(MigrationRunModel, model.run_id)
            authorization = session.get(CommandAuthorizationAuditModel, model.authorization_id)
            if run is None or authorization is None:
                self._fail_execution(session, model, "AUTHORIZATION_STALE", "Execution inputs disappeared")
                return
            self.transition_execution(session, model, CommandStatus.RUNNING.value)
            model.worker_id = worker_id
            self._append_event(session, model.run_id, model.stage_id, f"{model.id}:started",
                               WorkflowEventType.COMMAND_STARTED, "authorized command started",
                               {"execution_id": model.id, "worker_id": worker_id})

        cancel_event = threading.Event()
        lease_id: str | None = None
        heartbeat_stop = threading.Event()
        self._job_supervisor.register_cancel_event(execution_id, cancel_event)
        try:
            # Read and validate all process inputs in a short transaction. The
            # subprocess must never run while a repository session is open.
            with session_scope() as session:
                model = session.get(CommandExecutionModel, execution_id)
                run = session.get(MigrationRunModel, model.run_id) if model else None
                authorization = session.get(CommandAuthorizationAuditModel, model.authorization_id) if model else None
                if model is None or run is None or authorization is None:
                    return
                root = Path(run.run_root).resolve(strict=True)
                run_id = run.id
                stage_id = authorization.stage_id
                command_id = authorization.command_id
                executable = authorization.executable
                arguments = list(authorization.arguments or [])
                workspace_alias = authorization.workspace_alias
                execution_profile_id = authorization.execution_profile_id or ""
                timeout_seconds = model.timeout_seconds or self._default_timeout_seconds
                network_profile = authorization.network_profile or "none"
                idempotency_key = model.idempotency_key
                requested_at = model.requested_at
                correlation_id = model.correlation_id
                aliases = {
                    name: (root / path if not Path(path).is_absolute() else Path(path))
                    for name, path in (run.workspace_aliases or {}).items()
                }
                profile = session.scalar(select(ExecutionProfileModel).where(
                    ExecutionProfileModel.run_id == run.id,
                    ExecutionProfileModel.selected_profile_id == authorization.execution_profile_id,
                ).order_by(ExecutionProfileModel.created_at.desc()))
                if profile is None or profile.status not in {"resolved", "selected"}:
                    raise CommandExecutorError("EXECUTION_PROFILE_NOT_APPROVED", "Execution profile is not approved for this run")
                selected_profile = next(
                    (item for item in (profile.profiles or [])
                     if item.get("profile_id") == authorization.execution_profile_id
                     and item.get("checksum") == profile.selected_checksum),
                    None,
                )
                if selected_profile is None:
                    raise CommandExecutorError("EXECUTION_PROFILE_NOT_APPROVED", "Selected execution profile checksum is not current")
                lease = self._job_supervisor.acquire_lease(
                    session, run_id, execution_id, worker_id, worker_id,
                )
                lease_id = lease.lease_id
                if model.cancel_requested_at is not None:
                    cancel_event.set()
                artifact_root = Path(run.artifact_root)
                policy = CommandPolicy(
                    sandbox_root=root,
                    registry=CommandRegistry(),
                    working_directory_aliases=worker_workspace_aliases(aliases, workspace_alias),
                    environment_allowlist=tuple(selected_profile.get("environment_allowlist") or ("PATH",)),
                )
                store = LocalFilesystemArtifactStore(artifact_root, fixed_run_root=artifact_root)
                worker = ExecutionWorker(policy, CommandLogWriter(store, max_output_bytes=1_000_000), supervisor=self._supervisor)
                request = CommandRequestDto(
                    command_id=command_id,
                    run_id=run_id,
                    stage_id=stage_id,
                    requested_by=authorization.actor,
                    requester=authorization.actor,
                    executable=executable,
                    arguments=arguments,
                    shell=False,
                    working_directory_alias=workspace_alias,
                    runtime_profile_id=execution_profile_id,
                    timeout_seconds=timeout_seconds,
                    network_profile=network_profile,
                    cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
                    idempotency_key=idempotency_key,
                    requested_at=requested_at,
                )

            def renew_lease() -> None:
                from app.repositories.session import session_scope
                interval = max(1, self._job_supervisor._lease_seconds // 3)
                while not heartbeat_stop.wait(interval):
                    try:
                        with session_scope() as lease_session:
                            self._job_supervisor.renew_lease(lease_session, lease_id, worker_id)
                    except Exception:
                        cancel_event.set()
                        return

            heartbeat = threading.Thread(target=renew_lease, name=f"lease-heartbeat-{execution_id}", daemon=True)
            heartbeat.start()

            def persist_output(stream: str, text: str) -> None:
                from app.repositories.session import session_scope
                with session_scope() as log_session:
                    CommandLogService().append_chunk(
                        log_session, execution_id, run_id, stream, text,
                        correlation_id=correlation_id,
                        strict_ownership=True,
                    )

            result = worker.run(request, cancel_event=cancel_event, output_callback=persist_output)
            with session_scope() as session:
                model = session.get(CommandExecutionModel, execution_id)
                run = session.get(MigrationRunModel, run_id)
                authorization = session.get(CommandAuthorizationAuditModel, model.authorization_id) if model else None
                if model is None or run is None or authorization is None:
                    return
                self._finish_execution(session, model, result, run=run, authorization=authorization, profile=selected_profile)
        except Exception as exc:
            with session_scope() as session:
                model = session.get(CommandExecutionModel, execution_id)
                if model is not None and model.status not in {CommandStatus.SUCCEEDED.value, CommandStatus.FAILED.value, CommandStatus.CANCELLED.value, CommandStatus.TIMED_OUT.value}:
                    self._fail_execution(session, model, "EXECUTION_FAILED", str(exc))
        finally:
            heartbeat_stop.set()
            self._job_supervisor.unregister_cancel_event(execution_id)
            if lease_id is not None:
                try:
                    with session_scope() as lease_session:
                        self._job_supervisor.release_lease(lease_session, lease_id, worker_id)
                except Exception:
                    pass

    @staticmethod
    def _stage_belongs_to_run(session: Session, stage_id: str, run_id: str) -> bool:
        from app.repositories.models.workflow import MigrationStageModel
        stage = session.get(MigrationStageModel, stage_id)
        return stage is not None and stage.run_id == run_id

    def _finish_execution(self, session: Session, model: CommandExecutionModel, result, *, run, authorization, profile) -> None:
        finished = datetime.now(UTC)
        from app.services.command_log_service import CommandLogService
        log_service = CommandLogService()
        log_service.ensure_summary(session, model.id, model.run_id, correlation_id=model.correlation_id)
        log_service.finalize(session, model.id, finalized_at=finished)
        final_status = CommandStatus.TIMED_OUT.value if result.timed_out else result.result.status.value
        self.transition_execution(session, model, final_status, now=finished)
        model.exit_code = result.result.exit_code
        if model.status == CommandStatus.FAILED.value and model.failure_code is None:
            model.failure_code = "COMMAND_EXIT_NONZERO"
            model.failure_message = "The approved command exited with a non-zero status."
        if model.status == CommandStatus.CANCELLED.value:
            model.failure_code = "COMMAND_CANCELLED"
            model.failure_message = "Command cancelled; partial output was preserved."
        if model.status == CommandStatus.TIMED_OUT.value:
            model.failure_code = "COMMAND_TIMED_OUT"
            model.failure_message = "Command timed out; partial output was preserved."
        model.duration_ms = result.result.duration_ms
        model.timed_out = result.timed_out
        model.cancelled = result.cancelled
        model.command_log_artifact_id = result.command_log_artifact.ref.artifact_id
        model.stdout_artifact_id = result.stdout_artifact.ref.artifact_id if result.stdout_artifact else None
        model.stderr_artifact_id = result.stderr_artifact.ref.artifact_id if result.stderr_artifact else None
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        output_refs = [ref for ref in (result.stdout_artifact.ref, result.stderr_artifact.ref, result.command_log_artifact.ref)]
        result_payload = {
            "schema_version": "command-execution-result.v1", "execution_id": model.id,
            "run_id": model.run_id, "status": model.status, "exit_code": model.exit_code,
            "duration_ms": model.duration_ms, "timed_out": bool(model.timed_out),
            "cancelled": bool(model.cancelled), "failure_code": model.failure_code,
            "partial_evidence": bool(model.cancelled or model.timed_out),
            "artifact_ids": [ref.artifact_id for ref in output_refs],
        }
        result_artifact = store.write_text_artifact(
            run.id, f"04_workflow_state/command_executions/{model.id}.result.json",
            json.dumps(result_payload, indent=2, sort_keys=True), ArtifactType.REPORT,
            stage_id=model.stage_id, created_by="command-execution-worker", created_at=finished,
            content_type="application/json",
        )
        manifest_payload = {
            "schema_version": "command-execution-manifest.v1", "execution_id": model.id,
            "run_id": model.run_id, "stage_id": model.stage_id,
            "authorization_decision_id": authorization.id, "plan_id": authorization.plan_id,
            "plan_version": authorization.plan_version, "command_template_id": authorization.template_id,
            "command_template_version": authorization.template_version,
            "sanitized_command": {"executable": model.executable, "arguments": model.arguments, "shell": False},
            "execution_profile_id": model.runtime_profile_id, "workspace_alias": model.working_directory_alias,
            "safe_relative_working_directory": model.safe_relative_working_directory,
            "network_profile": model.network_profile, "authoritative_state_version": authorization.state_version,
            "worker_id": model.worker_id, "started_at": model.started_at.isoformat() if model.started_at else None,
            "ended_at": finished.isoformat(), "duration_ms": model.duration_ms, "status": model.status,
            "exit_code": model.exit_code, "artifact_ids": [ref.artifact_id for ref in output_refs] + [result_artifact.ref.artifact_id],
            "cancellation": {"requested": model.cancel_requested_at is not None, "cancelled": bool(model.cancelled), "timed_out": bool(model.timed_out), "partial_evidence": bool(model.cancelled or model.timed_out)},
            "runtime_identity": {"profile_checksum": profile.get("checksum") if isinstance(profile, dict) else None},
            "correlation_id": model.correlation_id,
        }
        manifest_artifact = store.write_text_artifact(
            run.id, f"04_workflow_state/command_executions/{model.id}.manifest.json",
            json.dumps(manifest_payload, indent=2, sort_keys=True), ArtifactType.JSON,
            stage_id=model.stage_id, created_by="command-execution-worker", created_at=finished,
        )
        all_artifacts = [
            item for item in (result.stdout_artifact, result.stderr_artifact, result.command_log_artifact, result_artifact, manifest_artifact)
            if item is not None
        ]
        for stored in all_artifacts:
            self._register_artifact_metadata(
                session, stored, execution_id=model.id, correlation_id=model.correlation_id,
                truncated=bool(stored.envelope.input_hashes.get("truncated", False)),
            )
        model.result_artifact_id = result_artifact.ref.artifact_id
        model.manifest_artifact_id = manifest_artifact.ref.artifact_id
        model.artifact_ids = [ref.artifact_id for ref in output_refs] + [result_artifact.ref.artifact_id, manifest_artifact.ref.artifact_id]
        model.runtime_checksum = (profile.get("checksum") if isinstance(profile, dict) and profile.get("checksum") else "sha256:" + hashlib.sha256(json.dumps(manifest_payload, sort_keys=True).encode()).hexdigest())
        event_type = (WorkflowEventType.COMMAND_CANCELLED if model.status == CommandStatus.CANCELLED.value else WorkflowEventType.COMMAND_INTERRUPTED if model.status == CommandStatus.TIMED_OUT.value else WorkflowEventType.COMMAND_SUCCEEDED if model.status == CommandStatus.SUCCEEDED.value else WorkflowEventType.COMMAND_FAILED)
        self._append_event(session, model.run_id, model.stage_id, f"{model.id}:completed", event_type,
                           f"command {model.status}", {"execution_id": model.id, "status": model.status,
                           "exit_code": model.exit_code, "artifact_ids": model.artifact_ids})
        if model.status in {CommandStatus.CANCELLED.value, CommandStatus.TIMED_OUT.value}:
            current_run = session.get(MigrationRunModel, model.run_id)
            if current_run is not None and current_run.status == "CANCELLING":
                from app.state.transition_service import StateTransitionService, TransitionRequest
                StateTransitionService(session).apply_transition(TransitionRequest(
                    run_id=model.run_id, idempotency_key=f"{model.id}:run-cancelled",
                    expected_state_version=current_run.state_version,
                    event_type=WorkflowEventType.RUN_CANCELLED,
                    next_run_status=RunStatus.CANCELLED,
                    actor="command-execution-worker",
                    reason="command cancellation completed; partial evidence retained",
                    occurred_at=finished,
                    payload={"execution_id": model.id, "partial_evidence": 1},
                ))

    @staticmethod
    def _register_artifact_metadata(session: Session, stored, *, execution_id: str, correlation_id: str | None, truncated: bool = False) -> None:
        payload = stored.content.encode("utf-8")
        session.add(ArtifactMetadataModel(
            id="metadata-" + stored.ref.artifact_id,
            run_id=stored.ref.run_id,
            stage_id=stored.ref.stage_id,
            artifact_type=stored.ref.artifact_type.value,
            relative_path=stored.ref.relative_path,
            checksum=stored.ref.checksum,
            schema_version=stored.envelope.schema_version,
            created_at=stored.ref.created_at,
            execution_id=execution_id,
            owner_reference=execution_id,
            mime_type=stored.envelope.content_type,
            size_bytes=len(payload),
            finalized_at=stored.ref.created_at,
            immutable=True,
            redacted=False,
            truncated=truncated,
            correlation_id=correlation_id,
            safe_metadata={"filename": Path(stored.ref.relative_path).name},
        ))

    def _fail_execution(self, session: Session, model: CommandExecutionModel, code: str, message: str) -> None:
        self.transition_execution(session, model, CommandStatus.FAILED.value)
        model.failure_code = code
        model.failure_message = message[:1000]
        model.blockers = [code]
        self._append_event(session, model.run_id, model.stage_id, f"{model.id}:failed", WorkflowEventType.COMMAND_FAILED,
                           message, {"execution_id": model.id, "error_code": code})

    def legacy_queue_command_disabled(
        self,
        session: Session,
        run_id: str,
        stage_id: str | None,
        command_id: str,
        executable: str,
        arguments: list[str],
        *,
        idempotency_key: str,
        requested_by: str | None = None,
        requester: str | None = None,
        working_directory_alias: str | None = None,
        working_directory: str | None = None,
        runtime_profile_id: str = "source-runtime-profile",
        timeout_seconds: int | None = None,
        network_profile: str = "none",
        cancellation_policy: str = "terminate_process_tree",
    ) -> CommandExecutionResponse:
        """Deprecated compatibility boundary; never executes commands.

        In Sprint 3, commands are executed synchronously within the
        request-response cycle for diagnostic commands. Async execution
        with live log streaming is added in S3-F03.
        """
        raise CommandExecutorError(
            "LEGACY_EXECUTION_DISABLED",
            "Use queue_authorized_command with an accepted authorization decision",
        )
        """
        # Check idempotency — same key + identical payload returns cached result
        existing = session.scalar(
            select(CommandExecutionModel)
            .where(CommandExecutionModel.run_id == run_id)
            .where(CommandExecutionModel.idempotency_key == idempotency_key)
        )
        if existing is not None:
            # Verify payload identity
            if (existing.executable == executable
                    and (existing.arguments or []) == (arguments or [])
                    and existing.command_id == command_id):
                return self._response_from_model(existing, idempotent_replay=True)
            raise CommandExecutorError(
                "IDEMPOTENCY_KEY_CONFLICT",
                f"Idempotency key '{idempotency_key}' already used with different payload",
            )

        effective_timeout = timeout_seconds or self._default_timeout_seconds
        now = datetime.now(UTC)

        # 1. Validate against policy engine
        policy_request = CommandPolicyValidateRequestDto(
            run_id=run_id,
            stage_id=stage_id,
            command_id=command_id,
            executable=executable,
            arguments=arguments or [],
            cwd_alias=working_directory_alias,
            plan_id=None,
            working_directory_alias=working_directory_alias,
            working_directory=working_directory,
            execution_profile_id=runtime_profile_id,
            network_profile=network_profile,
            cancellation_policy=cancellation_policy,
            timeout_seconds=effective_timeout,
            idempotency_key=idempotency_key,
            requested_by=requested_by,
            shell=False,
        )
        policy_result = self._policy_engine.validate(session, policy_request)
        if policy_result.decision == "rejected":
            raise CommandExecutorError(
                "POLICY_REJECTED",
                f"Command rejected by policy engine: {'; '.join(policy_result.reasons)}",
            )

        # 2. Create the execution record in QUEUED state
        execution_id = f"exec-{uuid4().hex[:12]}"
        exec_model = CommandExecutionModel(
            id=execution_id,
            run_id=run_id,
            stage_id=stage_id,
            authorization_id=policy_result.authorization_id,
            idempotency_key=idempotency_key,
            requested_by=requested_by,
            requester=requester,
            executable=executable,
            arguments=arguments,
            working_directory_alias=working_directory_alias,
            runtime_profile_id=runtime_profile_id,
            status=CommandStatus.PENDING.value,
            command_id=command_id,
            shell=False,
            timeout_seconds=effective_timeout,
            network_profile=network_profile,
            cancellation_policy=cancellation_policy,
            requested_at=now,
            state_version=1,
            event_sequence=1,
        )
        session.add(exec_model)
        session.flush()

        # 2. Emit COMMAND_QUEUED event
        self._append_event(session, run_id, stage_id, idempotency_key,
                           WorkflowEventType.COMMAND_QUEUED, "command queued for execution",
                           {"execution_id": execution_id, "command_id": command_id, "executable": executable})

        # 3. Update status to RUNNING
        exec_model.status = CommandStatus.RUNNING.value
        exec_model.state_version = (exec_model.state_version or 1) + 1
        exec_model.started_at = datetime.now(UTC)
        session.flush()

        # 4. Emit COMMAND_STARTED event
        self._append_event(session, run_id, stage_id, idempotency_key + ":started",
                           WorkflowEventType.COMMAND_STARTED, "command execution started",
                           {"execution_id": execution_id, "command_id": command_id})

        # 5. Build and run the command using the Sprint 0 WorkerSupervisor
        try:
            # Build a CommandRequestDto for the Sprint 0 worker
            request = CommandRequestDto(
                command_id=command_id,
                run_id=run_id,
                stage_id=stage_id,
                requested_by=requested_by,
                requester=requester or requested_by,
                executable=executable,
                arguments=arguments,
                shell=False,
                working_directory_alias=working_directory_alias,
                working_directory=working_directory,
                runtime_profile_id=runtime_profile_id,
                timeout_seconds=effective_timeout,
                network_profile=network_profile,
                cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
                idempotency_key=idempotency_key,
                requested_at=now,
            )

            # Find the command definition from registry
            registry = CommandRegistry()
            definition = registry.find(command_id)

            # Build working directory path
            sandbox_root = Path("/tmp/amfa-sandbox")
            sandbox_root.mkdir(parents=True, exist_ok=True)
            working_dir = sandbox_root
            if working_directory_alias:
                working_dir = sandbox_root / working_directory_alias.lower()
                working_dir.mkdir(parents=True, exist_ok=True)

            structured = StructuredCommandRequest(
                dto=request,
                definition=definition,
                command=(executable, *arguments),
                working_directory=working_dir,
            )

            # Create cancel event for this execution
            cancel_event = threading.Event()
            self._cancel_events[execution_id] = cancel_event

            supervised = self._supervisor.run(
                structured,
                cancel_event=cancel_event,
            )
            finished_at = datetime.now(UTC)

            # Clean up cancel event
            self._cancel_events.pop(execution_id, None)

            # 6. Update execution record
            status = self._map_supervised_status(supervised)
            exec_model.status = status.value
            exec_model.exit_code = supervised.exit_code
            exec_model.finished_at = finished_at
            exec_model.duration_ms = int((finished_at - now).total_seconds() * 1000)
            exec_model.timed_out = supervised.timed_out
            exec_model.cancelled = supervised.cancelled
            exec_model.state_version = (exec_model.state_version or 1) + 1

            # Compute runtime checksum from stdout+stderr output
            output_data = (supervised.stdout or "") + (supervised.stderr or "")
            exec_model.runtime_checksum = f"sha256:{hashlib.sha256(output_data.encode('utf-8')).hexdigest()}"

            # 7. Emit completion event
            event_type = {
                CommandStatus.SUCCEEDED: WorkflowEventType.COMMAND_SUCCEEDED,
                CommandStatus.FAILED: WorkflowEventType.COMMAND_FAILED,
                CommandStatus.CANCELLED: WorkflowEventType.COMMAND_INTERRUPTED,
                CommandStatus.TIMED_OUT: WorkflowEventType.COMMAND_INTERRUPTED,
            }.get(status, WorkflowEventType.COMMAND_FAILED)

            self._append_event(session, run_id, stage_id, idempotency_key + ":completed",
                               event_type, f"command {status.value}",
                               {"execution_id": execution_id, "command_id": command_id,
                                "exit_code": supervised.exit_code, "status": status.value})

            session.flush()

            return self._response_from_model(exec_model)

        except (CommandPolicyViolation, OSError) as exc:
            exec_model.status = CommandStatus.FAILED.value
            exec_model.finished_at = datetime.now(UTC)
            session.flush()
            self._append_event(session, run_id, stage_id, idempotency_key + ":failed",
                               WorkflowEventType.COMMAND_FAILED, str(exc),
                               {"execution_id": execution_id, "command_id": command_id, "error": str(exc)})
            return self._response_from_model(exec_model)

        """

    def get_command_execution(
        self,
        session: Session,
        run_id: str,
        execution_id: str,
    ) -> CommandExecutionModel | None:
        """Retrieve a command execution record."""
        return session.scalar(select(CommandExecutionModel).where(
            CommandExecutionModel.id == execution_id,
            CommandExecutionModel.run_id == run_id,
        ))

    def request_cancel(
        self,
        session: Session,
        run_id: str,
        execution_id: str,
        actor: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Cancel a running command execution.

        Sets the cancel event to terminate the OS process, then updates
        DB state and emits events via JobSupervisorService.
        """
        supervisor = self._job_supervisor
        legacy_event = self._cancel_events.get(execution_id)
        if legacy_event is not None:
            legacy_event.set()
        result = supervisor.cancel_command(
            session,
            run_id=run_id,
            execution_id=execution_id,
            actor=actor,
            idempotency_key=idempotency_key,
        )
        return result

    def get_list_command_executions(
        self,
        session: Session,
        run_id: str,
    ) -> list[CommandExecutionModel]:
        """List all command executions for a run."""
        return list(
            session.scalars(
                select(CommandExecutionModel)
                .where(CommandExecutionModel.run_id == run_id)
                .order_by(CommandExecutionModel.requested_at)
            )
        )

    @staticmethod
    def _map_supervised_status(supervised: SupervisedProcessResult) -> CommandStatus:
        if supervised.timed_out:
            return CommandStatus.TIMED_OUT
        if supervised.cancelled:
            return CommandStatus.CANCELLED
        if supervised.exit_code == 0:
            return CommandStatus.SUCCEEDED
        return CommandStatus.FAILED

    @staticmethod
    def _append_event(
        session: Session,
        run_id: str,
        stage_id: str | None,
        idempotency_key: str,
        event_type: WorkflowEventType,
        reason: str,
        payload: dict[str, Any],
    ) -> WorkflowEventModel:
        latest = session.scalar(
            select(WorkflowEventModel)
            .where(WorkflowEventModel.run_id == run_id)
            .order_by(WorkflowEventModel.sequence.desc())
            .limit(1)
        )
        event = WorkflowEventModel(
            id=f"event-{uuid4().hex[:12]}",
            run_id=run_id,
            stage_id=stage_id,
            event_type=event_type.value,
            idempotency_key=idempotency_key,
            actor="command-executor",
            reason=reason,
            sequence=(latest.sequence + 1) if latest else 1,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        session.add(event)
        return event

    @staticmethod
    def _response_from_model(
        model: CommandExecutionModel,
        *,
        idempotent_replay: bool = False,
    ) -> CommandExecutionResponse:
        return CommandExecutionResponse(
            execution_id=model.id,
            run_id=model.run_id,
            command_id=model.command_id,
            status=model.status,
            state_version=model.state_version or 1,
            event_sequence=model.event_sequence or 1,
            idempotent_replay=idempotent_replay,
            stage_id=model.stage_id,
            authorization_id=model.authorization_id,
            template_id=model.template_id,
            template_version=model.template_version,
            plan_id=model.plan_id,
            plan_version=model.plan_version,
            execution_profile_id=model.runtime_profile_id,
            workspace_alias=model.working_directory_alias,
            created_at=model.requested_at,
            started_at=model.started_at,
            completed_at=model.finished_at,
            duration_ms=model.duration_ms,
            exit_code=model.exit_code,
            failure_code=model.failure_code,
            failure_reason=model.failure_message,
            correlation_id=model.correlation_id,
            artifact_ids=tuple(model.artifact_ids or []),
            stdout_artifact_id=model.stdout_artifact_id,
            stderr_artifact_id=model.stderr_artifact_id,
            command_log_artifact_id=model.command_log_artifact_id,
            manifest_artifact_id=model.manifest_artifact_id,
            result_artifact_id=model.result_artifact_id,
            executable=model.executable,
            arguments=list(model.arguments or []),
            safe_relative_working_directory=model.safe_relative_working_directory,
            runtime_checksum=model.runtime_checksum,
            worker_id=model.worker_id,
            cancel_requested_at=model.cancel_requested_at,
            cancel_requested_by=model.cancel_requested_by,
            cancelled=bool(model.cancelled),
            timed_out=bool(model.timed_out),
            request_payload_hash=model.request_payload_hash,
        )
