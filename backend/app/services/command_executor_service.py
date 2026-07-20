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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import uuid4
from pathlib import Path
from typing import Any

from sqlalchemy import select
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
)
from app.repositories.models.workflow import (
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
from app.services.job_supervisor_service import JobSupervisorService


class CommandExecutorError(ValueError):
    """Raised when a command execution operation fails."""
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
        self._cancel_events: dict[str, threading.Event] = {}

    # The executor is process-owned, not request-owned.  This is deliberately
    # a small MVP worker pool; the durable execution row is the queue and the
    # worker always opens its own database session.
    _worker_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="amfa-command")

    def queue_authorized_command(
        self,
        session: Session,
        *,
        run_id: str,
        authorization_decision_id: str,
        expected_state_version: int,
        idempotency_key: str,
        requested_by: str | None = None,
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
            if existing.authorization_id != authorization_decision_id:
                raise CommandExecutorError("IDEMPOTENCY_KEY_CONFLICT", "Idempotency key is bound to another authorization")
            return self._response_from_model(existing, idempotent_replay=True)

        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise CommandExecutorError("RUN_NOT_FOUND", "Migration run does not exist")
        if run.state_version != expected_state_version:
            raise CommandExecutorError("STALE_STATE_VERSION", "The run state version is stale")

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
        if list(template.arguments) != list(authorization.arguments or []):
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

        now = datetime.now(UTC)
        execution_id = f"exec-{uuid4().hex[:12]}"
        model = CommandExecutionModel(
            id=execution_id,
            run_id=run_id,
            stage_id=authorization.stage_id,
            authorization_id=authorization.id,
            idempotency_key=idempotency_key,
            requested_by=requested_by or authorization.actor,
            executable=authorization.executable,
            arguments=list(authorization.arguments or []),
            working_directory_alias=authorization.workspace_alias,
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
        self._append_event(session, run_id, authorization.stage_id, idempotency_key,
                           WorkflowEventType.COMMAND_QUEUED, "authorized command queued",
                           {"execution_id": execution_id, "authorization_id": authorization.id,
                            "command_id": authorization.command_id, "state_version": run.state_version})
        return self._response_from_model(model)

    def dispatch_execution(self, execution_id: str) -> None:
        """Transfer a committed execution to the process-owned worker."""
        self._worker_pool.submit(self._run_execution, execution_id)

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
            model.status = CommandStatus.RUNNING.value
            model.started_at = datetime.now(UTC)
            model.worker_id = worker_id
            model.state_version = (model.state_version or 1) + 1
            self._append_event(session, model.run_id, model.stage_id, f"{model.id}:started",
                               WorkflowEventType.COMMAND_STARTED, "authorized command started",
                               {"execution_id": model.id, "worker_id": worker_id})

        cancel_event = threading.Event()
        self._cancel_events[execution_id] = cancel_event
        try:
            with session_scope() as session:
                model = session.get(CommandExecutionModel, execution_id)
                run = session.get(MigrationRunModel, model.run_id) if model else None
                authorization = session.get(CommandAuthorizationAuditModel, model.authorization_id) if model else None
                if model is None or run is None or authorization is None:
                    return
                root = Path(run.run_root).resolve(strict=True)
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
                policy = CommandPolicy(
                    sandbox_root=root,
                    registry=CommandRegistry(),
                    working_directory_aliases=aliases,
                    environment_allowlist=tuple(selected_profile.get("environment_allowlist") or ("PATH",)),
                )
                store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
                worker = ExecutionWorker(policy, CommandLogWriter(store, max_output_bytes=1_000_000), supervisor=self._supervisor)
                request = CommandRequestDto(
                    command_id=authorization.command_id,
                    run_id=run.id,
                    stage_id=authorization.stage_id,
                    requested_by=authorization.actor,
                    requester=authorization.actor,
                    executable=authorization.executable,
                    arguments=list(authorization.arguments or []),
                    shell=False,
                    working_directory_alias=authorization.workspace_alias,
                    runtime_profile_id=authorization.execution_profile_id or "",
                    timeout_seconds=model.timeout_seconds or self._default_timeout_seconds,
                    network_profile=authorization.network_profile or "none",
                    cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
                    idempotency_key=model.idempotency_key,
                    requested_at=model.requested_at,
                )
                result = worker.run(request, cancel_event=cancel_event)
                self._finish_execution(session, model, result)
        except Exception as exc:
            with session_scope() as session:
                model = session.get(CommandExecutionModel, execution_id)
                if model is not None and model.status not in {CommandStatus.SUCCEEDED.value, CommandStatus.FAILED.value, CommandStatus.CANCELLED.value, CommandStatus.TIMED_OUT.value}:
                    self._fail_execution(session, model, "EXECUTION_FAILED", str(exc))
        finally:
            self._cancel_events.pop(execution_id, None)

    @staticmethod
    def _stage_belongs_to_run(session: Session, stage_id: str, run_id: str) -> bool:
        from app.repositories.models.workflow import MigrationStageModel
        stage = session.get(MigrationStageModel, stage_id)
        return stage is not None and stage.run_id == run_id

    def _finish_execution(self, session: Session, model: CommandExecutionModel, result) -> None:
        finished = datetime.now(UTC)
        model.status = result.result.status.value
        model.exit_code = result.result.exit_code
        model.finished_at = finished
        model.duration_ms = result.result.duration_ms
        model.timed_out = result.timed_out
        model.cancelled = result.cancelled
        model.command_log_artifact_id = result.command_log_artifact.ref.artifact_id
        model.stdout_artifact_id = result.stdout_artifact.ref.artifact_id if result.stdout_artifact else None
        model.stderr_artifact_id = result.stderr_artifact.ref.artifact_id if result.stderr_artifact else None
        model.artifact_ids = [ref for ref in (model.command_log_artifact_id, model.stdout_artifact_id, model.stderr_artifact_id) if ref]
        model.runtime_checksum = "sha256:" + hashlib.sha256((result.result.model_dump_json()).encode()).hexdigest()
        model.state_version = (model.state_version or 1) + 1
        event_type = WorkflowEventType.COMMAND_SUCCEEDED if model.status == CommandStatus.SUCCEEDED.value else WorkflowEventType.COMMAND_FAILED
        self._append_event(session, model.run_id, model.stage_id, f"{model.id}:completed", event_type,
                           f"command {model.status}", {"execution_id": model.id, "status": model.status,
                           "exit_code": model.exit_code, "artifact_ids": model.artifact_ids})

    def _fail_execution(self, session: Session, model: CommandExecutionModel, code: str, message: str) -> None:
        model.status = CommandStatus.FAILED.value
        model.finished_at = datetime.now(UTC)
        model.blockers = [code]
        model.state_version = (model.state_version or 1) + 1
        self._append_event(session, model.run_id, model.stage_id, f"{model.id}:failed", WorkflowEventType.COMMAND_FAILED,
                           message, {"execution_id": model.id, "error_code": code})

    def queue_command(
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
        """Queue (and run synchronously) one approved command.

        In Sprint 3, commands are executed synchronously within the
        request-response cycle for diagnostic commands. Async execution
        with live log streaming is added in S3-F03.
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

    def get_command_execution(
        self,
        session: Session,
        run_id: str,
        execution_id: str,
    ) -> CommandExecutionModel | None:
        """Retrieve a command execution record."""
        model = session.get(CommandExecutionModel, execution_id)
        return model if model is not None and model.run_id == run_id else None

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
        # Set the cancel event for process termination
        cancel_event = self._cancel_events.get(execution_id)
        if cancel_event is not None:
            cancel_event.set()

        # Delegate to supervisor for DB updates and event emission
        supervisor = JobSupervisorService()
        return supervisor.cancel_command(
            session,
            run_id=run_id,
            execution_id=execution_id,
            actor=actor,
            idempotency_key=idempotency_key,
        )

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
        )
