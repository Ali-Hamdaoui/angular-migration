"""CommandExecutor application service for G01 S3-F02.

CommandExecutor wraps the Sprint 0 ExecutionWorker with proper
authorization, persistence, event emission, and artifact registration.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue

logger = logging.getLogger(__name__)
import re
import shutil
import signal
import subprocess
import threading
import traceback
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution.worker import (
    CommandDefinition,
    CommandLogWriter,
    CommandPolicy,
    CommandPolicyViolation,
    CommandRegistry,
    ExecutionWorker,
    StructuredCommandRequest,
    SupervisedProcessResult,
    WorkerSupervisor,
)
from app.core.config import get_settings
from app.domain.command import command_arguments_match
from app.domain.contracts import (
    ArtifactRefDto,
    ArtifactType,
    CancellationPolicy,
    CommandPolicyValidateRequestDto,
    CommandPolicyValidateResponseDto,
    CommandRequestDto,
    CommandResultDto,
    CommandStatus,
    RunStatus,
    WorkflowEventType,
)
from app.domain.runtime_execution import (
    RuntimeExecutableDescriptor,
    RuntimeExecutableKind,
    RuntimeRequirement,
)
from app.repositories.models import ExecutionProfileModel, StageExecutionPlanModel
from app.repositories.models.workflow import (
    ArtifactMetadataModel,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    MigrationRunModel,
    StagePromptRequestModel,
    WorkerLeaseModel,
    WorkflowEventModel,
)
from app.services.command_log_service import CommandLogService
from app.services.command_registry_service import (
    CommandPolicyEngineService,
    CommandRegistryService,
)
from app.services.job_supervisor_service import JobSupervisorService
from app.services.runtime_resolution_application_service import RuntimeResolutionApplicationService
from app.services.transformer_prompt_service import (
    AngularPromptDetector,
    TransformerPromptService,
)
from app.state.event_sequencer import append_workflow_event


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
_MUTATING_COMMAND_IDS = frozenset(
    {
        "npm-ci-bootstrap",
        "angular-update-exact",
        "npm-ci-final",
        "npm-lockfile-generate",
        "npm-dependency-uninstall",
        "npm-dependency-install",
    }
)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


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


def _profile_runtime_id(node_exact: str | None) -> str | None:
    """Derive a paired runtime id (``node<major>``) from a profile's exact node version."""
    if not node_exact:
        return None
    major = node_exact.split(".", 1)[0]
    return f"node{major}" if major.isdigit() else None


def _runtime_bindings_from_profile(profile: dict) -> dict[str, RuntimeExecutableDescriptor]:
    """Resolve PATH-independent, checksum-bound descriptors for the profile's runtimes.

    Returns an empty mapping when the profile cannot be satisfied by the runtime
    matrix; the command then keeps its existing resolution behavior.  When a
    binding IS returned, execution is fail-closed on descriptor mismatch.
    """
    runtime_id = _profile_runtime_id(profile.get("node_exact"))
    if runtime_id is None:
        return {}
    requirements = [
        RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id=runtime_id, version_exact=profile.get("node_exact")),
        RuntimeRequirement(kind=RuntimeExecutableKind.NPM, runtime_id=runtime_id, version_exact=profile.get("npm_exact")),
        RuntimeRequirement(kind=RuntimeExecutableKind.NPX, runtime_id=runtime_id, version_exact=profile.get("npx_exact")),
    ]
    service = RuntimeResolutionApplicationService(get_settings())
    bindings = {binding.descriptor.kind.value: binding.descriptor for binding in service.resolve(requirements) if binding.descriptor is not None}
    return bindings


def _runtime_path_overrides(bindings: dict[str, RuntimeExecutableDescriptor]) -> dict[str, str]:
    """Prepend bound runtime bin dirs to PATH so npm/npx resolve the same node."""
    if not bindings:
        return {}
    bin_dirs: list[str] = []
    for descriptor in bindings.values():
        bin_dir = (
            Path(descriptor.installation_root) / "bin"
            if descriptor.installation_root
            else Path(descriptor.resolved_path).parent
        )
        text = str(bin_dir)
        if text not in bin_dirs:
            bin_dirs.append(text)

    return {"PATH": os.pathsep.join([*bin_dirs, os.environ.get("PATH", "")])}


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
    claim_attempt: int | None = None


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
        runtime_resolution_service: RuntimeResolutionApplicationService | None = None,
    ) -> None:
        self._policy_engine = policy_engine or CommandPolicyEngineService()
        self._registry_service = registry_service or CommandRegistryService()
        self._supervisor = supervisor or WorkerSupervisor()
        self._default_timeout_seconds = default_timeout_seconds
        self._job_supervisor = JobSupervisorService()
        self._runtime_resolution = runtime_resolution_service
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
        CommandStatus.QUEUED.value: {
            CommandStatus.RUNNING.value,
            CommandStatus.FAILED.value,
            CommandStatus.CANCELLED.value,
        },
        CommandStatus.RUNNING.value: {
            CommandStatus.SUCCEEDED.value, CommandStatus.FAILED.value,
            CommandStatus.TIMED_OUT.value, CommandStatus.CANCELLED.value,
            CommandStatus.INTERRUPTED.value,
        },
        CommandStatus.INTERRUPTED.value: {CommandStatus.QUEUED.value, CommandStatus.FAILED.value},
        CommandStatus.SUCCEEDED.value: set(),
        CommandStatus.FAILED.value: set(),
        CommandStatus.TIMED_OUT.value: set(),
        CommandStatus.CANCELLED.value: set(),
    }

    # Bounded claim-loss budget: an execution whose lease expired this many
    # times is blocked instead of being requeued forever.
    _CLAIM_RETRY_THRESHOLD = 3

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

    def claim_next_execution(
        self,
        session: Session,
        worker_id: str,
        now: datetime | None = None,
        *,
        lease_seconds: int = 120,
    ) -> str | None:
        """Atomically claim the oldest durable queued command."""
        claimed_at = now or datetime.now(UTC)
        candidate = session.scalar(
            select(CommandExecutionModel)
            .where(CommandExecutionModel.status == CommandStatus.QUEUED.value)
            .where(
                or_(
                    CommandExecutionModel.worker_id.is_(None),
                    CommandExecutionModel.claim_expires_at <= claimed_at,
                )
            )
            .order_by(CommandExecutionModel.requested_at, CommandExecutionModel.id)
            .limit(1)
        )
        if candidate is None:
            return None
        expires_at = claimed_at + timedelta(seconds=lease_seconds)
        claimed = session.execute(
            update(CommandExecutionModel)
            .where(CommandExecutionModel.id == candidate.id)
            .where(CommandExecutionModel.status == CommandStatus.QUEUED.value)
            .where(
                or_(
                    CommandExecutionModel.worker_id.is_(None),
                    CommandExecutionModel.claim_expires_at <= claimed_at,
                )
            )
            .values(
                worker_id=worker_id,
                claim_attempt=(candidate.claim_attempt or 0) + 1,
                claim_expires_at=expires_at,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            session.expire_all()
            return None
        session.execute(
            delete(WorkerLeaseModel).where(
                WorkerLeaseModel.execution_id == candidate.id,
                WorkerLeaseModel.expires_at <= claimed_at,
            )
        )
        session.add(
            WorkerLeaseModel(
                id=f"lease-{uuid4().hex[:12]}",
                run_id=candidate.run_id,
                execution_id=candidate.id,
                worker_id=worker_id,
                lease_owner="transformer-worker",
                backend_instance_id=worker_id,
                acquired_at=claimed_at,
                heartbeat_at=claimed_at,
                expires_at=expires_at,
            )
        )
        session.flush()
        session.expire(candidate)
        return candidate.id

    def reconcile_expired_executions(
        self,
        session: Session,
        now: datetime | None = None,
    ) -> list[str]:
        """Recover expired claims without rerunning uncertain mutations."""
        checked_at = now or datetime.now(UTC)
        rows = list(
            session.scalars(
                select(CommandExecutionModel)
                .where(CommandExecutionModel.status.in_((CommandStatus.QUEUED.value, CommandStatus.RUNNING.value)))
                .where(CommandExecutionModel.worker_id.is_not(None))
                .where(CommandExecutionModel.claim_expires_at <= checked_at)
                .order_by(CommandExecutionModel.requested_at)
            )
        )
        recovered: list[str] = []
        for model in rows:
            prior_worker = model.worker_id
            model.worker_id = None
            model.claim_expires_at = None
            if (model.claim_attempt or 0) >= self._CLAIM_RETRY_THRESHOLD:
                model.status = CommandStatus.FAILED.value
                model.finished_at = checked_at
                model.failure_code = "COMMAND_CLAIM_EXHAUSTED"
                model.failure_message = (
                    "Command claim was lost repeatedly beyond the bounded claim-retry threshold."
                )
                model.blockers = [model.failure_code]
            elif model.status == CommandStatus.QUEUED.value:
                model.failure_code = None
                model.failure_message = None
            elif model.operation_kind == "mutating":
                model.status = CommandStatus.INTERRUPTED.value
                model.finished_at = checked_at
                model.reconstruction_required = True
                model.failure_code = "COMMAND_RECOVERY_REQUIRED"
                model.failure_message = "Worker lease expired during a mutating command; reconstruct before retry."
            else:
                model.status = CommandStatus.QUEUED.value
                model.started_at = None
                model.failure_code = "COMMAND_WORKER_LOST_REQUEUED"
                model.failure_message = "Read-only command lease expired before terminal evidence; command requeued."
            session.execute(
                delete(WorkerLeaseModel).where(
                    WorkerLeaseModel.execution_id == model.id,
                    WorkerLeaseModel.expires_at <= checked_at,
                )
            )
            self._append_event(
                session,
                model.run_id,
                model.stage_id,
                f"{model.id}:reconcile:{model.claim_attempt or 0}",
                WorkflowEventType.COMMAND_RECONSTRUCTION_REQUIRED
                if model.reconstruction_required
                else WorkflowEventType.COMMAND_INTERRUPTED,
                model.failure_message or "expired command claim recovered",
                {"execution_id": model.id, "worker_id": prior_worker, "status": model.status},
            )
            recovered.append(model.id)
        session.flush()
        return recovered

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
        timeout_seconds: int,
    ) -> CommandExecutionResponse:
        """Persist one execution from an accepted, immutable authorization.

        No command data is accepted from the caller.  The authorization audit,
        run, template, and profile are the only sources for execution inputs.
        ``timeout_seconds`` must be the exact policy-validated timeout of the
        authorized command request (the approved plan reference or the
        authorized command definition); it is persisted with the execution row
        and is never patched afterwards.
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
        if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise CommandExecutorError(
                "TIMEOUT_AUTHORITY_MISSING",
                "The authorized command timeout must be the validated positive timeout of the command request",
            )

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
            timeout_seconds=timeout_seconds,
            network_profile=authorization.network_profile or "none",
            cancellation_policy="terminate_process_tree",
            requested_at=now,
            state_version=1,
            event_sequence=1,
            worker_id=None,
            operation_kind="mutating" if authorization.command_id in _MUTATING_COMMAND_IDS else "read_only",
        )
        session.add(model)
        session.flush()
        self._append_event(session, run_id, authorization.stage_id, f"{idempotency_key}:queued",
                           WorkflowEventType.COMMAND_QUEUED, "authorized command queued",
                           {"execution_id": execution_id, "authorization_id": authorization.id,
                            "command_id": authorization.command_id, "state_version": run.state_version})
        return self._response_from_model(model)

    def resolve_authorized_timeout(
        self, session: Session, authorization_decision_id: str
    ) -> int:
        """Resolve the policy-validated timeout of an accepted authorization.

        The policy engine requires an approved-plan command's request timeout
        to equal the approved plan reference timeout, so the plan reference is
        the durable authority for the validated timeout.  Authorizations that
        do not belong to the approved plan (internal repair-transition or
        supersession authorizations) have no plan reference and fail closed;
        their callers always pass the timeout explicitly.
        """
        from app.repositories.planning_models import (
            MigrationPlanModel,
            StageExecutionPlanModel,
        )

        authorization = session.get(
            CommandAuthorizationAuditModel, authorization_decision_id
        )
        if authorization is None or authorization.decision != "accepted":
            raise CommandExecutorError(
                "AUTHORIZATION_DECISION_NOT_FOUND",
                "Authorization decision does not exist",
            )
        plan = session.scalar(
            select(MigrationPlanModel).where(
                MigrationPlanModel.id == authorization.plan_id,
                MigrationPlanModel.run_id == authorization.run_id,
            )
        )
        stage_plan = (
            session.scalar(
                select(StageExecutionPlanModel).where(
                    StageExecutionPlanModel.migration_plan_id == plan.id,
                    StageExecutionPlanModel.run_id == authorization.run_id,
                    StageExecutionPlanModel.stage_id == authorization.stage_id,
                    StageExecutionPlanModel.version == authorization.plan_version,
                )
            )
            if plan is not None
            else None
        )
        references = []
        if stage_plan is not None:
            references = [
                reference
                for group in ((stage_plan.stage_plan or {}).get("commands") or {}).values()
                for reference in group
            ]
        planned = next(
            (
                reference
                for reference in references
                if reference.get("command_id") == authorization.command_id
                and reference.get("template_id") == authorization.template_id
            ),
            None,
        )
        timeout = planned.get("timeout_seconds") if planned is not None else None
        if not isinstance(timeout, int) or timeout <= 0:
            raise CommandExecutorError(
                "TIMEOUT_AUTHORITY_MISSING",
                "The accepted authorization has no durable approved timeout",
            )
        return timeout

    def authorize_retry_command(
        self,
        session: Session,
        failed_execution_id: str,
        *,
        template_id: str,
        template_version: int,
        executable: str,
        arguments: list[str],
        working_directory_alias: str,
        working_directory: str,
        plan_id: str,
        plan_version: int,
        execution_profile_id: str,
        network_profile: str,
        timeout_seconds: int,
        idempotency_key: str,
    ) -> str:
        """Authorize a bounded command-template supersession before retrying."""
        failed = session.get(CommandExecutionModel, failed_execution_id)
        run = session.get(MigrationRunModel, failed.run_id) if failed is not None else None
        if failed is None or run is None:
            raise CommandExecutorError(
                "EXECUTION_NOT_FOUND", "Failed execution does not exist"
            )
        if failed.command_id != "angular-update-exact":
            raise CommandExecutorError(
                "ANGULAR_UPDATE_RETRY_INVALID",
                "Only an Angular update execution may receive v3 recovery authorization",
            )
        self._policy_engine.registry.seed_defaults(session)
        request = CommandPolicyValidateRequestDto(
            run_id=failed.run_id,
            expected_state_version=run.state_version,
            stage_id=failed.stage_id,
            command_id=failed.command_id,
            template_id=template_id,
            template_version=template_version,
            executable=executable,
            arguments=arguments,
            cwd_alias=working_directory_alias,
            plan_id=plan_id,
            plan_version=plan_version,
            working_directory_alias=working_directory_alias,
            working_directory=working_directory,
            execution_profile_id=execution_profile_id,
            network_profile=network_profile,
            cancellation_policy="terminate_process_tree",
            timeout_seconds=timeout_seconds,
            idempotency_key=idempotency_key,
            requested_by="transformer-recovery",
        )
        response = self._policy_engine.validate(
            session,
            request,
            supersedes_authorization_id=failed.authorization_id,
        )
        if response.decision != "accepted":
            raise CommandExecutorError(
                "AUTHORIZATION_REJECTED",
                "Angular v3 recovery authorization was rejected: "
                + "; ".join(response.reasons),
            )
        return response.authorization_id

    def authorize_dependency_transition_command(
        self,
        session: Session,
        *,
        attempt_id: str,
        command_id: str,
        executable: str,
        arguments: list[str],
        working_directory_alias: str,
        working_directory: str,
        plan_id: str,
        plan_version: int,
        execution_profile_id: str,
        network_profile: str,
        timeout_seconds: int,
        idempotency_key: str,
    ) -> str:
        """Authorize one detach/reattach command bound to an applied repair proposal."""
        from app.domain.command import (
            ANGULAR_UPDATE_V3_RENDERER,
            NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER,
            NPM_DEPENDENCY_INSTALL_RENDERER,
            NPM_DEPENDENCY_UNINSTALL_RENDERER,
            TRANSFORMATION_COMMAND_CATALOGUE,
        )
        from app.repositories.models.workflow import RepairAttemptModel

        attempt = session.get(RepairAttemptModel, attempt_id)
        run = session.get(MigrationRunModel, attempt.run_id) if attempt is not None else None
        if attempt is None or run is None:
            raise CommandExecutorError(
                "REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt does not exist"
            )
        renderer_for_command = {
            "npm-dependency-uninstall": (NPM_DEPENDENCY_UNINSTALL_RENDERER, 1),
            "npm-dependency-install": (NPM_DEPENDENCY_INSTALL_RENDERER, 1),
            "npm-angular-lockfile-normalize": (NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER, 2),
            "angular-update-exact": (ANGULAR_UPDATE_V3_RENDERER, 3),
        }
        renderer = renderer_for_command.get(command_id)
        if renderer is None:
            raise CommandExecutorError(
                "COMMAND_TEMPLATE_NOT_FOUND",
                "command has no dependency-transition renderer",
            )
        template, template_version = renderer
        self._policy_engine.registry.seed_defaults(session)
        request = CommandPolicyValidateRequestDto(
            run_id=attempt.run_id,
            expected_state_version=run.state_version,
            stage_id=attempt.stage_id,
            command_id=command_id,
            template_id=template.template_id,
            template_version=template_version,
            executable=executable,
            arguments=arguments,
            cwd_alias=working_directory_alias,
            plan_id=plan_id,
            plan_version=plan_version,
            working_directory_alias=working_directory_alias,
            working_directory=working_directory,
            execution_profile_id=execution_profile_id,
            network_profile=network_profile,
            cancellation_policy="terminate_process_tree",
            timeout_seconds=timeout_seconds,
            idempotency_key=idempotency_key,
            requested_by="transformer-recovery",
        )
        response = self._policy_engine.validate(
            session,
            request,
            repair_transition_attempt_id=attempt_id,
        )
        if response.decision != "accepted":
            raise CommandExecutorError(
                "AUTHORIZATION_REJECTED",
                "Dependency transition command authorization was rejected: "
                + "; ".join(response.reasons),
            )
        return response.authorization_id

    def queue_retry_execution(
        self,
        session: Session,
        failed_execution_id: str,
        *,
        idempotency_key: str,
        workspace_recovered: bool = False,
        replacement_authorization_id: str | None = None,
        checkpoint_id: str | None = None,
        authorized_timeout_seconds: int,
    ) -> CommandExecutionResponse:
        """Create one immutable successor for a failed or interrupted execution.

        ``authorized_timeout_seconds`` is the freshly validated timeout of the
        successor's own authorization (or, absent a replacement authorization,
        the current authorized command definition).  It is never inherited
        from the historical failed execution row, which remains immutable
        evidence only.
        """
        failed = session.get(CommandExecutionModel, failed_execution_id)
        if failed is None:
            raise CommandExecutorError("EXECUTION_NOT_FOUND", "Failed execution does not exist")
        if (
            not isinstance(authorized_timeout_seconds, int)
            or authorized_timeout_seconds <= 0
        ):
            raise CommandExecutorError(
                "TIMEOUT_AUTHORITY_MISSING",
                "A retry requires the freshly validated timeout of its own authorization",
            )
        existing = session.scalar(
            select(CommandExecutionModel).where(
                CommandExecutionModel.run_id == failed.run_id,
                CommandExecutionModel.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.parent_execution_id != failed.id:
                raise CommandExecutorError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "Retry key is bound to another execution",
                )
            return self._response_from_model(existing, idempotent_replay=True)
        if replacement_authorization_id and (
            failed.command_id != "angular-update-exact"
            or failed.template_version != 2
        ):
            raise CommandExecutorError(
                "ANGULAR_UPDATE_RETRY_INVALID",
                "Only an accepted v2 Angular update may be superseded by v3",
            )
        if replacement_authorization_id and failed.template_version == 2:
            existing_successor = session.scalar(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == failed.run_id,
                    CommandExecutionModel.parent_execution_id == failed.id,
                    CommandExecutionModel.template_version == 3,
                )
            )
            if existing_successor is not None:
                raise CommandExecutorError(
                    "ANGULAR_UPDATE_V3_RETRY_ALREADY_EXECUTED",
                    "The version-3 Angular recovery is already bound to this failed execution",
                )
        if failed.status in {
            CommandStatus.INTERRUPTED.value,
            CommandStatus.TIMED_OUT.value,
        }:
            if not failed.reconstruction_required:
                raise CommandExecutorError(
                    "EXECUTION_NOT_RETRYABLE",
                    "An interrupted or timed-out execution may only have a successor after reconstruction is required and verified",
                )
        elif failed.status != CommandStatus.FAILED.value:
            raise CommandExecutorError(
                "EXECUTION_NOT_RETRYABLE",
                "Only a terminal failed execution may have a successor",
            )
        if (failed.attempt_number or 1) >= self._retry_budget(session, failed):
            raise CommandExecutorError(
                "REQUESTED_RETRY_EXCEEDS_LIMIT",
                "Requested retry exceeds the stage plan repair policy retry budget",
            )
        if (
            failed.process_id is not None or failed.exit_code is not None
        ) and not workspace_recovered:
            raise CommandExecutorError(
                "EXECUTION_RETRY_REQUIRES_RECOVERY",
                "A command with process evidence requires verified workspace recovery",
            )
        active = session.scalar(
            select(CommandExecutionModel).where(
                CommandExecutionModel.run_id == failed.run_id,
                CommandExecutionModel.status.in_(
                    (
                        CommandStatus.PENDING.value,
                        CommandStatus.QUEUED.value,
                        CommandStatus.RUNNING.value,
                    )
                ),
            )
        )
        if active is not None:
            raise CommandExecutorError(
                "ACTIVE_COMMAND_EXISTS",
                "The run already has an active command",
            )
        authorization = session.get(
            CommandAuthorizationAuditModel,
            replacement_authorization_id or failed.authorization_id,
        )
        if authorization is None or authorization.decision != "accepted":
            raise CommandExecutorError(
                "AUTHORIZATION_STALE",
                "The original accepted authorization is unavailable",
            )
        if (
            replacement_authorization_id
            and (
                authorization.run_id != failed.run_id
                or authorization.stage_id != failed.stage_id
                or authorization.command_id != failed.command_id
                or authorization.template_id != "tpl-angular-update-exact-v3"
                or authorization.template_version != 3
            )
        ):
            raise CommandExecutorError(
                "AUTHORIZATION_STALE",
                "The replacement authorization does not supersede the failed command",
            )

        now = datetime.now(UTC)
        successor = CommandExecutionModel(
            id=f"exec-{uuid4().hex[:12]}",
            run_id=failed.run_id,
            stage_id=failed.stage_id,
            authorization_id=authorization.id,
            template_id=authorization.template_id,
            template_version=authorization.template_version,
            plan_id=authorization.plan_id,
            plan_version=authorization.plan_version,
            idempotency_key=idempotency_key,
            request_payload_hash=authorization.request_payload_hash,
            correlation_id=failed.correlation_id,
            requested_by=authorization.actor or failed.requested_by,
            executable=authorization.executable,
            arguments=list(authorization.arguments or []),
            working_directory_alias=authorization.workspace_alias,
            safe_relative_working_directory=failed.safe_relative_working_directory,
            runtime_profile_id=authorization.execution_profile_id,
            status=CommandStatus.QUEUED.value,
            requested_at=now,
            command_id=authorization.command_id,
            shell=False,
            timeout_seconds=authorized_timeout_seconds,
            network_profile=authorization.network_profile,
            cancellation_policy=failed.cancellation_policy,
            state_version=1,
            event_sequence=1,
            worker_id=None,
            operation_kind=failed.operation_kind,
            checkpoint_id=checkpoint_id or failed.checkpoint_id,
            prompt_request_id=None,
            authoritative_state_version=failed.authoritative_state_version,
            parent_execution_id=failed.id,
            attempt_number=(failed.attempt_number or 1) + 1,
        )
        session.add(successor)
        session.flush()
        self._append_event(
            session,
            successor.run_id,
            successor.stage_id,
            f"{idempotency_key}:queued",
            WorkflowEventType.COMMAND_QUEUED,
            "authorized command retry queued",
            {
                "execution_id": successor.id,
                "parent_execution_id": failed.id,
                "attempt_number": successor.attempt_number,
                "authorization_id": successor.authorization_id,
                "command_id": successor.command_id,
                "template_id": successor.template_id,
                "template_version": successor.template_version,
                "supersedes_authorization_id": failed.authorization_id
                if replacement_authorization_id
                else None,
            },
        )
        return self._response_from_model(successor)

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

    def execute_claimed_execution(self, execution_id: str, worker_id: str) -> None:
        """Execute a command already claimed by this durable worker."""
        self._run_execution(execution_id, worker_id)

    def _run_execution(self, execution_id: str, claimed_worker_id: str | None = None) -> None:
        from app.repositories.session import session_scope
        worker_id = claimed_worker_id or threading.current_thread().name
        with session_scope() as session:
            model = session.get(CommandExecutionModel, execution_id)
            if (
                model is None
                or model.status != CommandStatus.QUEUED.value
                or (claimed_worker_id is not None and model.worker_id != claimed_worker_id)
            ):
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
                existing_lease = session.scalar(
                    select(WorkerLeaseModel).where(
                        WorkerLeaseModel.execution_id == execution_id,
                        WorkerLeaseModel.worker_id == worker_id,
                        WorkerLeaseModel.expires_at > datetime.now(UTC),
                    )
                )
                if existing_lease is None:
                    lease = self._job_supervisor.acquire_lease(
                        session, run_id, execution_id, worker_id, worker_id,
                    )
                    lease_id = lease.lease_id
                else:
                    lease_id = existing_lease.id
                if model.cancel_requested_at is not None:
                    cancel_event.set()
                prompt_stdin = None
                if model.prompt_request_id:
                    prompt = session.get(StagePromptRequestModel, model.prompt_request_id)
                    prompt_stdin = TransformerPromptService.selected_stdin(prompt) if prompt else None
                artifact_root = Path(run.artifact_root)
                store = LocalFilesystemArtifactStore(artifact_root, fixed_run_root=artifact_root)
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

            # Fail-closed runtime binding: resolve the profile's executables to
            # PATH-independent, checksum-bound descriptors.  Probing runs
            # outside the database session (no transaction across processes).
            runtime_bindings = _runtime_bindings_from_profile(selected_profile)
            if runtime_bindings:
                policy = CommandPolicy(
                    sandbox_root=root,
                    registry=CommandRegistry(),
                    working_directory_aliases=worker_workspace_aliases(aliases, workspace_alias),
                    runtime_profiles=frozenset({execution_profile_id}),
                    network_profiles=frozenset({network_profile}),
                    environment_allowlist=tuple(selected_profile.get("environment_allowlist") or ("PATH",)),
                    environment_overrides=_runtime_path_overrides(runtime_bindings),
                    runtime_bindings=runtime_bindings,
                )
                worker = ExecutionWorker(policy, CommandLogWriter(store, max_output_bytes=1_000_000), supervisor=self._supervisor)
                self._record_runtime_bindings_evidence(run_id, runtime_bindings, execution_id=execution_id)
            else:
                policy = CommandPolicy(
                    sandbox_root=root,
                    registry=CommandRegistry(),
                    working_directory_aliases=worker_workspace_aliases(aliases, workspace_alias),
                    runtime_profiles=frozenset({execution_profile_id}),
                    network_profiles=frozenset({network_profile}),
                    environment_allowlist=tuple(selected_profile.get("environment_allowlist") or ("PATH",)),
                )
                worker = ExecutionWorker(policy, CommandLogWriter(store, max_output_bytes=1_000_000), supervisor=self._supervisor)

            def renew_lease() -> None:
                from app.repositories.session import session_scope
                interval = max(1, self._job_supervisor._lease_seconds // 3)
                while not heartbeat_stop.wait(interval):
                    try:
                        with session_scope() as lease_session:
                            renewed = self._job_supervisor.renew_lease(lease_session, lease_id, worker_id)
                            durable_execution = lease_session.get(CommandExecutionModel, execution_id)
                            if durable_execution is None or durable_execution.cancel_requested_at is not None:
                                cancel_event.set()
                            lease_session.execute(
                                update(CommandExecutionModel)
                                .where(
                                    CommandExecutionModel.id == execution_id,
                                    CommandExecutionModel.worker_id == worker_id,
                                    CommandExecutionModel.status == CommandStatus.RUNNING.value,
                                )
                                .values(claim_expires_at=renewed.expires_at)
                            )
                    except Exception:
                        cancel_event.set()
                        return

            heartbeat = threading.Thread(target=renew_lease, name=f"lease-heartbeat-{execution_id}", daemon=True)
            heartbeat.start()

            prompt_buffer = ""
            prompt_captured = False

            def persist_output(stream: str, text: str) -> None:
                nonlocal prompt_buffer, prompt_captured
                from app.repositories.session import session_scope
                with session_scope() as log_session:
                    CommandLogService().append_chunk(
                        log_session, execution_id, run_id, stream, text,
                        correlation_id=correlation_id,
                        strict_ownership=True,
                    )
                    if command_id == "angular-update-exact" and not prompt_captured:
                        prompt_buffer = (prompt_buffer + text)[-8192:]
                        detected = AngularPromptDetector().detect(prompt_buffer)
                        if detected is not None:
                            durable = log_session.get(CommandExecutionModel, execution_id)
                            TransformerPromptService().capture(log_session, durable, detected)
                            prompt_captured = True
                            cancel_event.set()

            def persist_pid(process_id: int) -> None:
                from app.repositories.session import session_scope
                with session_scope() as process_session:
                    persisted = process_session.execute(
                        update(CommandExecutionModel)
                        .where(
                            CommandExecutionModel.id == execution_id,
                            CommandExecutionModel.status == CommandStatus.RUNNING.value,
                            CommandExecutionModel.worker_id == worker_id,
                        )
                        .values(process_id=process_id)
                    )
                    if persisted.rowcount != 1:
                        raise CommandExecutorError(
                            "COMMAND_CLAIM_STALE",
                            "Process started after its command claim became stale",
                        )

            result = worker.run(
                request,
                cancel_event=cancel_event,
                output_callback=persist_output,
                process_started_callback=persist_pid,
                stdin_text=prompt_stdin,
            )
            with session_scope() as session:
                model = session.get(CommandExecutionModel, execution_id)
                run = session.get(MigrationRunModel, run_id)
                authorization = session.get(CommandAuthorizationAuditModel, model.authorization_id) if model else None
                if model is None or run is None or authorization is None:
                    return
                self._finish_execution(session, model, result, run=run, authorization=authorization, profile=selected_profile)
        except Exception as exc:
            causal_traceback = traceback.format_exc()
            with session_scope() as session:
                model = session.get(CommandExecutionModel, execution_id)
                if model is not None and model.status not in {CommandStatus.SUCCEEDED.value, CommandStatus.FAILED.value, CommandStatus.CANCELLED.value, CommandStatus.TIMED_OUT.value}:
                    self._persist_internal_failure(
                        session,
                        model,
                        exc,
                        causal_traceback,
                    )
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
        final_status = (
            CommandStatus.FAILED.value
            if result.result.status == CommandStatus.REJECTED
            else CommandStatus.TIMED_OUT.value
            if result.timed_out
            else result.result.status.value
        )
        terminal_statuses = {
            CommandStatus.SUCCEEDED.value,
            CommandStatus.FAILED.value,
            CommandStatus.TIMED_OUT.value,
            CommandStatus.CANCELLED.value,
        }
        if model.status in terminal_statuses:
            if (
                model.status == final_status
                and model.exit_code == result.result.exit_code
                and model.duration_ms == result.result.duration_ms
                and bool(model.timed_out) == bool(result.timed_out)
                and bool(model.cancelled) == bool(result.cancelled)
            ):
                return
            raise CommandExecutorError(
                "TERMINAL_RESULT_CONFLICT",
                "Terminal callback conflicts with immutable command evidence",
                {
                    "execution_id": model.id,
                    "persisted_status": model.status,
                    "callback_status": final_status,
                },
            )
        from app.services.command_log_service import CommandLogService
        log_service = CommandLogService()
        log_service.ensure_summary(session, model.id, model.run_id, correlation_id=model.correlation_id)
        log_service.finalize(session, model.id, finalized_at=finished)
        model.exit_code = result.result.exit_code
        if final_status == CommandStatus.FAILED.value and model.failure_code is None:
            if result.result.status == CommandStatus.REJECTED:
                model.failure_code = "COMMAND_PRESPAWN_FAILED"
                model.failure_message = self._result_failure_message(
                    result,
                    "Command preparation failed before process spawn.",
                )
            elif result.result.exit_code is None:
                model.failure_code = "COMMAND_START_FAILED"
                model.failure_message = self._result_failure_message(
                    result,
                    "Unable to start the approved command.",
                )
            else:
                model.failure_code = "COMMAND_EXIT_NONZERO"
                model.failure_message = self._result_failure_message(
                    result,
                    "The approved command exited with a non-zero status.",
                )
            model.blockers = [model.failure_code]
        if final_status == CommandStatus.CANCELLED.value:
            model.failure_code = "COMMAND_CANCELLED"
            model.failure_message = "Command cancelled; partial output was preserved."
        if final_status == CommandStatus.TIMED_OUT.value:
            model.failure_code = "COMMAND_TIMED_OUT"
            model.failure_message = "Command timed out; partial output was preserved."
        # A mutating command that terminated without verified success may have
        # left the workspace partially changed. It must never feed another
        # governed mutating/repair step until the workspace is reconstructed
        # against an authorized checkpoint, so mark it reconstruction-required.
        if (
            final_status in {CommandStatus.TIMED_OUT.value, CommandStatus.CANCELLED.value}
            and model.operation_kind == "mutating"
        ):
            model.reconstruction_required = True
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
            "run_id": model.run_id, "status": final_status, "exit_code": model.exit_code,
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
            "ended_at": finished.isoformat(), "duration_ms": model.duration_ms, "status": final_status,
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
        session.flush()
        # Command evidence is durable before the terminal transition; a
        # terminal CAS failure must never erase command evidence.
        session.commit()
        model = session.get(CommandExecutionModel, model.id)
        # The terminal status transition, command row update, and the
        # terminal COMMAND_* event are committed together in ONE transaction.
        # There is no post-commit event append that a later rollback could
        # silently discard.
        self.transition_execution(session, model, final_status, now=finished)
        event_type = (WorkflowEventType.COMMAND_CANCELLED if model.status == CommandStatus.CANCELLED.value else WorkflowEventType.COMMAND_INTERRUPTED if model.status == CommandStatus.TIMED_OUT.value else WorkflowEventType.COMMAND_SUCCEEDED if model.status == CommandStatus.SUCCEEDED.value else WorkflowEventType.COMMAND_FAILED)
        self._append_event(session, model.run_id, model.stage_id, f"{model.id}:completed", event_type,
                           f"command {model.status}", {"execution_id": model.id, "status": model.status,
                           "exit_code": model.exit_code, "artifact_ids": model.artifact_ids})
        session.commit()
        # The optional RUN_CANCELLED run-level CAS runs in its own
        # transaction AFTER the terminal event is committed: a stale run
        # state version can only roll back the cancellation CAS, never the
        # terminal command event.
        if model.status in {CommandStatus.CANCELLED.value, CommandStatus.TIMED_OUT.value}:
            current_run = session.get(MigrationRunModel, model.run_id)
            if current_run is not None and current_run.status == "CANCELLING":
                from app.state.transition_service import (
                    StaleStateVersionError,
                    StateTransitionService,
                    TransitionRequest,
                )
                try:
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
                    session.commit()
                except StaleStateVersionError:
                    session.rollback()

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
        model.failure_code = model.failure_code or code
        model.failure_message = model.failure_message or message[:1000]
        model.blockers = model.blockers or [model.failure_code]
        self._append_event(session, model.run_id, model.stage_id, f"{model.id}:failed", WorkflowEventType.COMMAND_FAILED,
                           model.failure_message, {"execution_id": model.id, "error_code": model.failure_code})

    def _persist_internal_failure(
        self,
        session: Session,
        model: CommandExecutionModel,
        error: Exception,
        causal_traceback: str,
    ) -> None:
        CommandLogService().append_chunk(
            session,
            model.id,
            model.run_id,
            "system",
            causal_traceback,
            correlation_id=model.correlation_id,
            strict_ownership=True,
        )
        model.failure_code = model.failure_code or getattr(
            error,
            "code",
            "EXECUTION_FAILED",
        )
        model.failure_message = model.failure_message or str(error)[:1000]
        model.blockers = model.blockers or [model.failure_code]
        model.duration_ms = self._elapsed_ms(model.started_at)

    @staticmethod
    def _result_failure_message(result, fallback: str) -> str:
        if result.stderr_artifact and result.stderr_artifact.content.strip():
            raw = _ANSI_ESCAPE.sub("", result.stderr_artifact.content)
            if (
                result.result.command_id == "angular-update-exact"
                and result.result.exit_code is not None
                and result.result.exit_code != 0
            ):
                # Keep the whole failure tail: the peer-dependency detail block
                # sits above the "Migration failed" summary line, so slicing
                # from the marker would discard the evidence the classifier
                # needs. The last 2000 chars of the stripped stderr contain
                # both the detail block and the final summary.
                return raw.strip()[-2000:]
            return raw.strip()[:1000]
        return fallback

    @staticmethod
    def _elapsed_ms(started_at: datetime | None) -> int | None:
        if started_at is None:
            return None
        now = datetime.now(UTC)
        if started_at.tzinfo is None:
            now = now.replace(tzinfo=None)
        return max(0, round((now - started_at).total_seconds() * 1000))

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
    def _retry_budget(session: Session, execution: CommandExecutionModel) -> int:
        """Resolve the bounded retry budget from the stage plan repair policy."""
        stage_plan = session.scalar(
            select(StageExecutionPlanModel)
            .where(
                StageExecutionPlanModel.run_id == execution.run_id,
                StageExecutionPlanModel.stage_id == execution.stage_id,
            )
            .order_by(StageExecutionPlanModel.version.desc())
            .limit(1)
        )
        repair_policy = (
            ((stage_plan.stage_plan or {}).get("repair_policy") or {})
            if stage_plan is not None
            else {}
        )
        try:
            budget = int(repair_policy.get("max_attempts") or 3)
        except (TypeError, ValueError):
            budget = 3
        return max(1, budget)

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
        return append_workflow_event(
            session,
            run_id=run_id,
            stage_id=stage_id,
            event_type=event_type.value,
            idempotency_key=idempotency_key,
            actor="command-executor",
            reason=reason,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )

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
            claim_attempt=model.claim_attempt,
        )

    def _record_runtime_bindings_evidence(
        self, run_id: str, bindings: dict[str, RuntimeExecutableDescriptor], *, execution_id: str | None
    ) -> None:
        """Persist the resolved runtime descriptors as durable execution evidence."""
        try:
            service = self._runtime_resolution or RuntimeResolutionApplicationService(get_settings())
            self._runtime_resolution = service
            from app.domain.runtime_execution import RuntimeRequirementBinding

            service.record_evidence(
                run_id,
                [
                    RuntimeRequirementBinding(
                        requirement=RuntimeRequirement(
                            kind=descriptor.kind,
                            runtime_id=descriptor.runtime_id or descriptor.kind.value,
                            version_exact=descriptor.version_exact,
                        ),
                        descriptor=descriptor,
                    )
                    for descriptor in bindings.values()
                ],
                execution_id=execution_id,
                actor="command-executor-service",
            )
        except Exception as exc:
            # Evidence recording must never fail the command itself; the failure
            # is still surfaced to operators through logs.
            logger.warning("Failed to persist runtime execution evidence for run %s: %s", run_id, exc)
