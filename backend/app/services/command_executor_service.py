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
    CommandExecutionModel,
    WorkflowEventModel,
)
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
        return session.get(CommandExecutionModel, execution_id)

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
