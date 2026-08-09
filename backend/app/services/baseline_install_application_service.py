"""Asynchronous, durable baseline installation application service."""
from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.baseline_contracts import BaselineInstallCancelRequest, BaselineInstallRequest, BaselineInstallResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandDefinition, CommandLogWriter, CommandPolicy, CommandRegistry, ExecutionWorker
from app.domain.baseline_installation import BaselineInstallPrerequisites, BaselineInstallationError, BaselineInstallationService, FrozenBaselineCommandPolicy, FrozenBaselineInspectionService
from app.domain.contracts import ArtifactType, CommandStatus, WorkflowEventType
from app.repositories.g02_models import G02ApprovalModel
from app.repositories.models import ArtifactMetadataModel, BaselineQualificationModel, CommandExecutionModel, ExecutionProfileModel, MigrationRunModel, WorkerLeaseModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, StaleStateVersionError, TransitionRequest
from app.workspaces.baseline import BaselineSandboxService


class BaselineInstallApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message); self.code = code; self.message = message; self.status_code = status_code


class BaselineInstallApplicationService:
    POLICY_VERSION = "baseline-install-v1"

    def __init__(self, *, session_scope_factory=session_scope, worker_factory=None, now_provider=None, g05_service=None) -> None:
        self._scope = session_scope_factory; self._worker_factory = worker_factory; self._now = now_provider or (lambda: datetime.now(UTC))
        self._g05 = g05_service
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="baseline-install")
        self._cancel_events: dict[str, threading.Event] = {}
        self._output_buffers: dict[str, dict[str, list[str]]] = {}
        self._lock = threading.Lock()
        self._backend_instance_id = f"backend-{os.getpid()}-{uuid4().hex[:8]}"

    def accept(self, run_id: str, request: BaselineInstallRequest) -> BaselineInstallResponse:
        prepared = self._prepare(run_id, request)
        if isinstance(prepared, BaselineInstallResponse): return prepared
        execution_id, sandbox, before, command = prepared
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[execution_id] = cancel_event
            self._output_buffers[execution_id] = {"stdout": [], "stderr": []}
        self._executor.submit(self._execute, run_id, execution_id, request, sandbox, before, command, cancel_event)
        return self.get(run_id, execution_id)  # type: ignore[return-value]

    def install(self, run_id: str, request: BaselineInstallRequest) -> BaselineInstallResponse:
        prepared = self._prepare(run_id, request)
        if isinstance(prepared, BaselineInstallResponse): return prepared
        execution_id, sandbox, before, command = prepared
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[execution_id] = cancel_event
            self._output_buffers[execution_id] = {"stdout": [], "stderr": []}
        return self._execute(run_id, execution_id, request, sandbox, before, command, cancel_event)

    def cancel(self, run_id: str, execution_id: str, request: BaselineInstallCancelRequest) -> BaselineInstallResponse:
        with self._scope() as session:
            record = session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id, CommandExecutionModel.id == execution_id))
            if record is None: raise BaselineInstallApplicationError("COMMAND_EXECUTION_NOT_FOUND", "Command execution was not found.", 404)
            if record.status not in {CommandStatus.PENDING.value, CommandStatus.RUNNING.value}: return self._response(record)
            if record.cancel_idempotency_key == request.idempotency_key: return self._response(record)
            run = self._run(session, run_id)
            if run.state_version != request.expected_state_version: raise BaselineInstallApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)
            record.cancel_requested_at = self._now()
            record.cancel_requested_by = request.actor
            record.cancel_idempotency_key = request.idempotency_key
            session.flush()
        with self._lock:
            event = self._cancel_events.get(execution_id)
            if event is None: raise BaselineInstallApplicationError("COMMAND_NOT_ACTIVE", "The command is no longer supervised.", 409)
            event.set()
        return self.get(run_id, execution_id)  # type: ignore[return-value]

    def get(self, run_id: str, execution_id: str) -> BaselineInstallResponse | None:
        with self._scope() as session:
            record = session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id, CommandExecutionModel.id == execution_id))
            return self._response(record) if record is not None else None

    def _prepare(self, run_id: str, request: BaselineInstallRequest):
        queued_at = self._now()
        with self._scope() as session:
            run = self._run(session, run_id)
            existing = self._existing(session, run_id, request.idempotency_key)
            if existing is not None:
                if existing.runtime_profile_id != request.runtime_profile_id or existing.runtime_checksum != request.runtime_checksum or existing.timeout_seconds != request.timeout_seconds: raise BaselineInstallApplicationError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different install request.", 409)
                return self._response(existing, idempotent_replay=True)
            baseline = self._baseline(session, run_id)
            if baseline is None: raise BaselineInstallApplicationError("BASELINE_WORKSPACE_REQUIRED", "Baseline qualification is required.", 409)
            if baseline.authorization_status != "authorized": raise BaselineInstallApplicationError("BASELINE_INSTALL_AUTHORIZATION_REQUIRED", "Baseline installation authorization is required.", 409)
            if baseline.blockers: raise BaselineInstallApplicationError("BASELINE_INSTALL_BLOCKED", "Blocked baseline prequalification cannot be installed.", 409)
            if run.state_version != request.expected_state_version: raise BaselineInstallApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)
            if self._g05 is not None:
                try:
                    self._g05.require_approved_g05(run_id, expected_state_version=request.expected_state_version, workspace_fingerprint=None, plan_version=None, actor=request.actor)
                except Exception as error:
                    raise BaselineInstallApplicationError(getattr(error, "code", "G05_APPROVAL_REQUIRED"), "An approved current G05 gate is required before baseline installation.", 409) from error
            g02 = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.updated_at.desc()))
            if g02 is None or g02.status not in {"approved", "approved_with_comment"}: raise BaselineInstallApplicationError("BASELINE_G02_REQUIRED", "Approved G02 evidence is required.", 409)
            aliases = run.workspace_aliases or {}
            if not aliases.get("BASELINE_SANDBOX"): raise BaselineInstallApplicationError("BASELINE_LAYOUT_REQUIRED", "Registered baseline sandbox alias is required.", 409)
            profile = self._profile(session, run_id, request.runtime_profile_id, request.runtime_checksum)
            if profile is None: raise BaselineInstallApplicationError("EXECUTION_PROFILE_REQUIRED", "The selected execution profile checksum is required.", 409)
            lockfile = baseline.lockfile or {}
            if lockfile.get("status") not in {"valid", "qualified"}: raise BaselineInstallApplicationError("BASELINE_LOCKFILE_REQUIRED", "A valid lockfile is required before installation.", 409)
            sandbox = Path(aliases["BASELINE_SANDBOX"])
            if not sandbox.is_dir() or sandbox.resolve() != Path(baseline.sandbox_path).resolve(): raise BaselineInstallApplicationError("BASELINE_WORKSPACE_BOUNDARY", "The registered baseline sandbox does not match the qualified sandbox.", 409)
            before = FrozenBaselineInspectionService().inspect_before(sandbox)
            expected_lock = lockfile.get("lockfile_checksum")
            if expected_lock and before[1].checksum != expected_lock: raise BaselineInstallApplicationError("BASELINE_LOCKFILE_STALE", "The baseline lockfile checksum no longer matches the qualified artifact.", 409)
            selected_executable = next((item.get("package_manager_executable", "npm") for item in profile.profiles if item.get("profile_id") == profile.selected_profile_id and item.get("checksum") == profile.selected_checksum), "npm")
            command = FrozenBaselineCommandPolicy(selected_executable).create()
            queued = self._transition(session, run, request, WorkflowEventType.COMMAND_QUEUED, "baseline npm ci command queued", {"command_id": command.command_id})
            record = CommandExecutionModel(id=f"execution-{uuid4().hex[:12]}", run_id=run_id, stage_id=None, idempotency_key=request.idempotency_key, requested_by=request.actor, requester=request.actor, command_id=command.command_id, executable=command.executable, arguments=list(command.arguments), shell=False, working_directory_alias=command.working_directory_alias, runtime_profile_id=request.runtime_profile_id, runtime_checksum=request.runtime_checksum, baseline_checksum=baseline.checksum, timeout_seconds=request.timeout_seconds, network_profile=command.network_profile, cancellation_policy="terminate_process_tree", status=CommandStatus.PENDING.value, requested_at=queued_at, artifact_ids=[], blockers=[], state_version=queued.next_state_version, event_sequence=queued.event_sequence, start_fingerprint={"package_json": asdict(before[0]), "lockfile": asdict(before[1])})
            session.add(record); session.flush()
            return record.id, sandbox, before, command

    def _execute(self, run_id, execution_id, request, sandbox, before, command, cancel_event):
        heartbeat_stop = threading.Event()
        heartbeat_thread = None
        try:
            with self._scope() as session:
                run = self._run(session, run_id); record = session.get(CommandExecutionModel, execution_id)
                started = self._transition(session, run, request, WorkflowEventType.COMMAND_STARTED, "baseline npm ci command started", {"execution_id": execution_id}, expected_state_version=record.state_version)
                record.status = CommandStatus.RUNNING.value; record.state_version = started.next_state_version; record.event_sequence = started.event_sequence; record.worker_id = f"{threading.current_thread().name}:pid-{os.getpid()}"
                session.add(WorkerLeaseModel(id=f"lease-{uuid4().hex[:12]}", run_id=run_id, execution_id=execution_id, worker_id=record.worker_id, lease_owner=record.worker_id, backend_instance_id=self._backend_instance_id, acquired_at=self._now(), heartbeat_at=self._now(), expires_at=self._now() + timedelta(seconds=request.timeout_seconds)))
            heartbeat_thread = threading.Thread(target=self._heartbeat_loop, args=(execution_id, heartbeat_stop, request.timeout_seconds), daemon=True)
            heartbeat_thread.start()
            worker = self._worker(self._run_by_id(run_id), request.runtime_profile_id, command.executable, self._runtime_environment(run_id, request.runtime_profile_id, request.runtime_checksum))
            command_request = command.request(run_id=run_id, runtime_profile_id=request.runtime_profile_id, timeout_seconds=request.timeout_seconds, idempotency_key=request.idempotency_key, actor=request.actor, requested_at=self._now())
            result = BaselineInstallationService(worker, command_policy=FrozenBaselineCommandPolicy(command.executable)).execute(command_request, sandbox=sandbox, prerequisites=BaselineInstallPrerequisites(True, True, True, True, True), cancel_event=cancel_event, output_callback=lambda stream, chunk: self._output_chunk(run_id, execution_id, request, stream, chunk))
            if result.command.result.status is CommandStatus.FAILED and result.command.result.exit_code is None:
                return self._finalize_failure(run_id, execution_id, request, before, sandbox, "BASELINE_INSTALL_ENVIRONMENT_BLOCKED", environment_blocker="PROCESS_START_FAILED")
            return self._finalize(run_id, execution_id, request, before, result)
        except BaselineInstallationError as error: return self._finalize_failure(run_id, execution_id, request, before, sandbox, error.code)
        except OSError: return self._finalize_failure(run_id, execution_id, request, before, sandbox, "BASELINE_INSTALL_ENVIRONMENT_BLOCKED", environment_blocker="PROCESS_START_FAILED")
        except Exception as error: return self._finalize_failure(run_id, execution_id, request, before, sandbox, "BASELINE_INSTALL_EXECUTION_FAILED", detail=str(error), reconstruct_workspace=True)
        finally:
            heartbeat_stop.set()
            if heartbeat_thread is not None: heartbeat_thread.join(timeout=1)
            with self._lock: self._cancel_events.pop(execution_id, None)

    def _heartbeat_loop(self, execution_id, stop_event, timeout_seconds):
        interval = max(0.25, min(30.0, timeout_seconds / 3))
        while not stop_event.wait(interval):
            with self._scope() as session:
                lease = session.scalar(select(WorkerLeaseModel).where(WorkerLeaseModel.execution_id == execution_id).order_by(WorkerLeaseModel.acquired_at.desc()))
                if lease is None: return
                now = self._now()
                lease.heartbeat_at = now
                lease.expires_at = now + timedelta(seconds=timeout_seconds)
                session.flush()
    def reconcile_orphans(self) -> int:
        """Recover orphaned executions using persisted fingerprints and leases."""
        recovered = 0
        with self._scope() as session:
            records = session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.status.in_([CommandStatus.PENDING.value, CommandStatus.RUNNING.value]))).all()
            for record in records:
                run = self._run(session, record.run_id)
                request = BaselineInstallRequest(expected_state_version=record.state_version, idempotency_key=record.idempotency_key or f"supervisor-recovery:{record.id}", actor="baseline-supervisor", runtime_profile_id=record.runtime_profile_id or "unknown", runtime_checksum=record.runtime_checksum or "unknown", timeout_seconds=record.timeout_seconds or 3600)
                action = "reconstruct"
                reconstruction = self._reconstruct_baseline(session, run, record.id)
                try:
                    completed = self._transition(session, run, request, WorkflowEventType.COMMAND_INTERRUPTED, "worker lease was lost during restart recovery", {"execution_id": record.id, "worker_id": record.worker_id, "recovery_action": action, "reconstruction_required": True}, expected_state_version=run.state_version)
                except BaselineInstallApplicationError:
                    continue
                record.status = CommandStatus.FAILED.value
                record.finished_at = self._now()
                record.cancelled = False
                record.reconstruction_required = True
                record.blockers = ["BASELINE_RECONSTRUCTED"] if reconstruction.get("status") == "reconstructed" else [reconstruction.get("blocker", "BASELINE_RECONSTRUCTION_FAILED")]
                record.state_version = completed.next_state_version
                record.event_sequence = completed.event_sequence
                for lease in session.scalars(select(WorkerLeaseModel).where(WorkerLeaseModel.execution_id == record.id)).all(): session.delete(lease)
                recovered += 1
            session.flush()
        return recovered
    def _output_chunk(self, run_id, execution_id, request, stream, chunk):
        redacted = self._redact(chunk)
        with self._lock:
            self._output_buffers.setdefault(execution_id, {"stdout": [], "stderr": []}).setdefault(stream, []).append(redacted)
        with self._scope() as session:
            run = self._run(session, run_id)
            transition = self._transition(session, run, request, WorkflowEventType.COMMAND_OUTPUT_CHUNK, "baseline command output chunk", {"execution_id": execution_id, "stream": stream, "chunk": self._bound_live_chunk(redacted)}, expected_state_version=run.state_version)
            record = session.get(CommandExecutionModel, execution_id)
            if record is not None:
                record.state_version = transition.next_state_version
                record.event_sequence = transition.event_sequence

    @staticmethod
    def _bound_live_chunk(value: str, limit: int = 64_000) -> str:
        encoded = value.encode("utf-8")
        suffix = "\n[output chunk truncated]"
        if len(encoded) <= limit:
            return value
        return encoded[:max(0, limit - len(suffix.encode()))].decode("utf-8", errors="replace") + suffix

    def _reconstruct_baseline(self, session, run, execution_id):
        baseline = self._baseline(session, run.id)
        aliases = run.workspace_aliases or {}
        snapshot_raw = aliases.get("SOURCE_SNAPSHOT")
        baseline_raw = aliases.get("BASELINE_SANDBOX")
        if baseline is None or not snapshot_raw or not baseline_raw or not Path(snapshot_raw).is_dir() or not run.run_root:
            return {"status": "failed", "execution_id": execution_id, "blocker": "BASELINE_RECONSTRUCTION_INPUTS_MISSING"}
        try:
            workspace = BaselineSandboxService().reconstruct(run_id=run.id, snapshot_root=Path(snapshot_raw), baseline_path=Path(baseline_raw), approved_snapshot_fingerprint=baseline.input_fingerprint, registered_run_root=Path(run.run_root))
            baseline.sandbox_fingerprint = workspace.fingerprint
            baseline.updated_at = self._now()
            return {"status": "reconstructed", "execution_id": execution_id, "fingerprint": workspace.fingerprint, "excluded_paths": list(workspace.excluded_paths)}
        except Exception as error:
            return {"status": "failed", "execution_id": execution_id, "blocker": "BASELINE_RECONSTRUCTION_FAILED", "detail": str(error)}

    def _finalize(self, run_id, execution_id, request, before, result):
        with self._scope() as session:
            run = self._run(session, run_id)
            record = session.get(CommandExecutionModel, execution_id)
            reconstruction = self._reconstruct_baseline(session, run, execution_id) if result.inspection.reconstruction_required else {"status": "not_required"}
            artifacts = self._persist_artifacts(session, run, result, request, execution_id, reconstruction, executable=record.executable)
            status = result.command.result.status
            record.status = status.value
            record.started_at = result.command.result.started_at
            record.finished_at = result.command.result.finished_at
            record.duration_ms = result.command.result.duration_ms
            record.exit_code = result.command.result.exit_code
            record.timed_out = result.command.timed_out
            record.cancelled = result.command.cancelled
            record.reconstruction_required = result.inspection.reconstruction_required
            record.start_fingerprint = {"package_json": asdict(before[0]), "lockfile": asdict(before[1])}
            record.end_fingerprint = {"package_json": asdict(result.inspection.package_json), "lockfile": asdict(result.inspection.lockfile)}
            record.blockers = list(result.inspection.blockers)
            if reconstruction.get("status") == "failed": record.blockers.append(reconstruction.get("blocker", "BASELINE_RECONSTRUCTION_FAILED"))
            record.artifact_ids = artifacts
            record.command_log_artifact_id = result.command.command_log_artifact.ref.artifact_id
            record.stdout_artifact_id = result.command.stdout_artifact.ref.artifact_id if result.command.stdout_artifact else None
            record.stderr_artifact_id = result.command.stderr_artifact.ref.artifact_id if result.command.stderr_artifact else None
            output = self._transition(session, run, request, WorkflowEventType.COMMAND_OUTPUT_AVAILABLE, "baseline npm ci output finalized", {"execution_id": execution_id, "artifact_count": len(artifacts)}, expected_state_version=record.state_version)
            event_type = WorkflowEventType.BASELINE_INSTALL_SUCCEEDED if status is CommandStatus.SUCCEEDED and not record.blockers and reconstruction.get("status") != "failed" else WorkflowEventType.COMMAND_INTERRUPTED if result.command.timed_out else WorkflowEventType.COMMAND_CANCELLED if result.command.cancelled else WorkflowEventType.BASELINE_INSTALL_FAILED
            completed = self._transition(session, run, request, event_type, "baseline npm ci command completed", {"execution_id": execution_id, "status": record.status, "reconstruction_status": reconstruction.get("status")}, expected_state_version=output.next_state_version)
            record.state_version = completed.next_state_version
            record.event_sequence = completed.event_sequence
            return self._response(record)

    def _finalize_failure(self, run_id, execution_id, request, before, sandbox, blocker, *, environment_blocker=None, detail=None, reconstruct_workspace=False):
        with self._scope() as session:
            run = self._run(session, run_id)
            record = session.get(CommandExecutionModel, execution_id)
            inspection = FrozenBaselineInspectionService()
            after = inspection.inspect_before(sandbox) if sandbox.is_dir() else before
            reconstruction = self._reconstruct_baseline(session, run, execution_id) if reconstruct_workspace else {"status": "not_required"}
            artifacts = self._persist_failure_artifacts(session, run, request, execution_id, before, after, blocker, environment_blocker, detail, reconstruction)
            record.status = CommandStatus.FAILED.value
            record.finished_at = self._now()
            record.environment_blocker = environment_blocker
            record.reconstruction_required = reconstruct_workspace
            record.start_fingerprint = {"package_json": asdict(before[0]), "lockfile": asdict(before[1])}
            record.end_fingerprint = {"package_json": asdict(after[0]), "lockfile": asdict(after[1])}
            record.blockers = [blocker] + ([reconstruction.get("blocker")] if reconstruction.get("status") == "failed" else [])
            record.artifact_ids = artifacts
            record.command_log_artifact_id = artifacts[0] if len(artifacts) > 0 else None
            record.stdout_artifact_id = artifacts[1] if len(artifacts) > 1 else None
            record.stderr_artifact_id = artifacts[2] if len(artifacts) > 2 else None
            completed = self._transition(session, run, request, WorkflowEventType.BASELINE_INSTALL_FAILED, "baseline npm ci command failed before completion", {"execution_id": execution_id, "blocker": blocker, "reconstruction_status": reconstruction.get("status")}, expected_state_version=record.state_version)
            record.state_version = completed.next_state_version
            record.event_sequence = completed.event_sequence
            return self._response(record)

    def _write_artifact(self, store, run, path, content, artifact_type, request):
        return store.write_text_artifact(run.id, path, content, artifact_type, created_by="baseline-install-application-service", created_at=self._now(), input_hashes={"request": request.idempotency_key, "baseline": request.runtime_checksum})

    def _persist_failure_artifacts(self, session, run, request, execution_id, before, after, blocker, environment_blocker, detail, reconstruction):
        root = Path(run.artifact_root).resolve()
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        with self._lock:
            buffers = self._output_buffers.pop(execution_id, {"stdout": [], "stderr": []})
        security = self._dependency_security_summary(
            "".join((*buffers.get("stdout", []), *buffers.get("stderr", [])))
        )
        artifacts = [
            self._write_artifact(store, run, "04_workflow_state/command_logs/npm-ci-bootstrap-failure.json", json.dumps({"command_id": "npm-ci-bootstrap", "status": "FAILED", "blocker": blocker, "environment_blocker": environment_blocker, "detail": detail}, indent=2), ArtifactType.COMMAND_LOG, request),
            self._write_artifact(store, run, "04_workflow_state/command_logs/npm-ci-bootstrap-failure.stdout.log", "".join(buffers.get("stdout", [])), ArtifactType.TEXT_LOG, request),
            self._write_artifact(store, run, "04_workflow_state/command_logs/npm-ci-bootstrap-failure.stderr.log", "".join(buffers.get("stderr", [])), ArtifactType.TEXT_LOG, request),
            self._write_artifact(store, run, "01_baseline/lockfile_post_install_verification.json", json.dumps({"package_json": asdict(after[0]), "lockfile": asdict(after[1]), "unchanged": after == before}, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/dependency-security-summary.json", json.dumps(security, indent=2), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/baseline_install_summary.json", json.dumps({"status": "failed", "blockers": [blocker], "risks": security["risks"], "environment_blocker": environment_blocker, "fingerprints": {"start": {"package_json": asdict(before[0]), "lockfile": asdict(before[1])}, "end": {"package_json": asdict(after[0]), "lockfile": asdict(after[1])}}, "reconstruction": reconstruction}, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/npm_ci_authorization.json", json.dumps({"status": "authorized", "runtime_profile_id": request.runtime_profile_id, "runtime_checksum": request.runtime_checksum}, indent=2), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/npm_ci_command_manifest.json", json.dumps({"command_id": "npm-ci-bootstrap", "executable": "npm", "arguments": ["ci"], "working_directory_alias": "BASELINE_SANDBOX", "runtime_profile_id": request.runtime_profile_id, "runtime_checksum": request.runtime_checksum}, indent=2), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/npm_ci_result.json", json.dumps({"status": "failed", "blockers": [blocker], "environment_blocker": environment_blocker, "detail": detail}, indent=2), ArtifactType.JSON, request),
        ]
        artifacts.extend([
            self._write_artifact(store, run, "01_baseline/npm_ci_stdout.log", "".join(buffers.get("stdout", [])), ArtifactType.TEXT_LOG, request),
            self._write_artifact(store, run, "01_baseline/npm_ci_stderr.log", "".join(buffers.get("stderr", [])), ArtifactType.TEXT_LOG, request),
            self._write_artifact(store, run, "01_baseline/npm_ci_command_log.json", json.dumps({"command_id": "npm-ci-bootstrap", "status": "failed", "blocker": blocker}, indent=2), ArtifactType.COMMAND_LOG, request),
        ])
        self._register_artifacts(session, run, artifacts)
        return [a.ref.artifact_id for a in artifacts]

    @staticmethod
    def _npm_cache_paths(run):
        aliases = run.workspace_aliases or {}
        sandbox = Path(aliases.get("BASELINE_SANDBOX", ""))
        config_files = []
        if sandbox.is_dir(): config_files.append(sandbox / ".npmrc")
        for variable in ("NPM_CONFIG_USERCONFIG", "npm_config_userconfig", "NPM_CONFIG_GLOBALCONFIG", "npm_config_globalconfig"):
            value = os.environ.get(variable)
            if value: config_files.append(Path(value).expanduser())
        config_files.extend([Path.home() / ".npmrc", Path.home() / "AppData" / "Roaming" / "npm" / "etc" / "npmrc"])
        caches = {Path(value).expanduser() for value in (os.environ.get("npm_config_cache"), os.environ.get("NPM_CONFIG_CACHE")) if value}
        for config_file in config_files:
            try:
                for raw_line in config_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or line.startswith(";") or "=" not in line: continue
                    key, value = line.split("=", 1)
                    if key.strip().lower() != "cache": continue
                    candidate = Path(os.path.expandvars(value.strip())).expanduser()
                    caches.add(candidate if candidate.is_absolute() else (config_file.parent / candidate).resolve())
            except OSError:
                continue
        caches.update({Path.home() / "AppData" / "Local" / "npm-cache", Path.home() / "AppData" / "Roaming" / "npm-cache"})
        return tuple(caches)

    @staticmethod
    def _npm_debug_log_paths(run, result):
        aliases = run.workspace_aliases or {}
        candidates = []
        sandbox = Path(aliases.get("BASELINE_SANDBOX", ""))
        if sandbox.is_dir(): candidates.extend(sandbox.glob("npm-debug.log*"))
        for cache in BaselineInstallApplicationService._npm_cache_paths(run):
            candidates.extend(cache.glob("_logs/*.log"))
        started = result.command.result.started_at.timestamp()
        finished = (result.command.result.finished_at or datetime.now(UTC)).timestamp()
        unique = {}
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                if resolved.is_file() and started - 1 <= resolved.stat().st_mtime <= finished + 1: unique[str(resolved)] = resolved
            except OSError:
                continue
        return tuple(unique.values())
    @staticmethod
    def _register_artifacts(session, run, artifacts):
        for artifact in artifacts:
            session.add(ArtifactMetadataModel(id=f"metadata-{artifact.ref.artifact_id}", run_id=run.id, stage_id=None, artifact_type=artifact.ref.artifact_type.value, relative_path=artifact.ref.relative_path, checksum=artifact.ref.checksum, created_at=artifact.ref.created_at, finalized_at=artifact.ref.created_at, immutable=True))
    def _persist_artifacts(self, session, run, result, request, execution_id, reconstruction, *, executable="npm"):
        root = Path(run.artifact_root).resolve()
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        artifacts = [result.command.command_log_artifact]
        if result.command.stdout_artifact: artifacts.append(result.command.stdout_artifact)
        if result.command.stderr_artifact: artifacts.append(result.command.stderr_artifact)
        command_manifest = {"command_id": "npm-ci-bootstrap", "executable": executable, "arguments": ["ci"], "working_directory_alias": "BASELINE_SANDBOX", "runtime_profile_id": request.runtime_profile_id, "runtime_checksum": request.runtime_checksum}
        dependency_tree = asdict(result.inspection.dependency_tree) if result.inspection.dependency_tree else {"status": "not_run"}
        result_payload = {"status": result.command.result.status.value, "exit_code": result.command.result.exit_code, "timed_out": result.command.timed_out, "cancelled": result.command.cancelled, "blockers": list(result.inspection.blockers)}
        security = self._dependency_security_summary(
            "\n".join(
                artifact.content
                for artifact in (result.command.stdout_artifact, result.command.stderr_artifact)
                if artifact is not None
            )
        )
        artifacts.extend([
            self._write_artifact(store, run, "01_baseline/npm_ci_authorization.json", json.dumps({"status": "authorized", "runtime_profile_id": request.runtime_profile_id, "runtime_checksum": request.runtime_checksum}, indent=2), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/npm_ci_command_manifest.json", json.dumps(command_manifest, indent=2), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/npm-ci-command.json", json.dumps(command_manifest, indent=2), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/dependency_tree.json", json.dumps(dependency_tree, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/dependency_tree_verification.json", json.dumps(dependency_tree, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/npm_ci_result.json", json.dumps(result_payload, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/lockfile_post_install_verification.json", json.dumps({"package_json": asdict(result.inspection.package_json), "lockfile": asdict(result.inspection.lockfile), "unchanged": not result.inspection.blockers}, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/dependency-security-summary.json", json.dumps(security, indent=2), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/baseline_install_summary.json", json.dumps({"status": result.inspection.status, "blockers": list(result.inspection.blockers), "risks": security["risks"], "reconstruction": reconstruction}, indent=2, default=str), ArtifactType.JSON, request),
        ])
        if result.command.stdout_artifact:
            artifacts.append(self._write_artifact(store, run, "01_baseline/npm_ci_stdout.log", result.command.stdout_artifact.content, ArtifactType.TEXT_LOG, request))
        if result.command.stderr_artifact:
            artifacts.append(self._write_artifact(store, run, "01_baseline/npm_ci_stderr.log", result.command.stderr_artifact.content, ArtifactType.TEXT_LOG, request))
        artifacts.append(self._write_artifact(store, run, "01_baseline/npm_ci_command_log.json", result.command.command_log_artifact.content, ArtifactType.COMMAND_LOG, request))
        for index, debug_path in enumerate(self._npm_debug_log_paths(run, result)):
            try:
                artifacts.append(self._write_artifact(store, run, f"01_baseline/npm-debug/{index:03d}-{debug_path.name}", self._redact(debug_path.read_text(encoding="utf-8", errors="replace")), ArtifactType.TEXT_LOG, request))
            except OSError:
                continue
        self._register_artifacts(session, run, artifacts)
        with self._lock: self._output_buffers.pop(execution_id, None)
        return [a.ref.artifact_id for a in artifacts]

    @staticmethod
    def _dependency_security_summary(output: str) -> dict[str, object]:
        severity_counts = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
        summary = re.search(r"(?im)^\s*(?:found\s+)?(\d+)\s+vulnerabilit(?:y|ies)\b(?:\s*\(([^)]*)\))?", output)
        if summary is None:
            return {
                "source": "npm-ci-output",
                "status": "not_reported",
                "total": 0,
                "severity_counts": severity_counts,
                "policy_decision": "report_only",
                "risks": [],
                "blockers": [],
            }
        for count, severity in re.findall(
            r"(\d+)\s+(low|moderate|high|critical)\b",
            summary.group(2) or "",
            re.IGNORECASE,
        ):
            severity_counts[severity.lower()] = int(count)
        total = int(summary.group(1))
        risks = ["DEPENDENCY_VULNERABILITIES_REPORTED"] if total else []
        return {
            "source": "npm-ci-output",
            "status": "risk_detected" if total else "no_risk_detected",
            "total": total,
            "severity_counts": severity_counts,
            "policy_decision": "report_only",
            "risks": risks,
            "blockers": [],
        }
    def _worker(self, run, runtime_profile_id, executable="npm", environment_overrides=None):
        if self._worker_factory is not None: return self._worker_factory(run)
        baseline = Path((run.workspace_aliases or {})["BASELINE_SANDBOX"]).resolve(); root = Path(run.artifact_root).resolve(); store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        definitions = tuple(CommandDefinition(item.command_id, executable if item.command_id == "npm-ci-bootstrap" else item.executable, item.arguments, tuple(dict.fromkeys((*item.executable_aliases, "npm", "npm.cmd", executable)))) if item.command_id == "npm-ci-bootstrap" else item for item in CommandRegistry().definitions)
        policy = CommandPolicy(sandbox_root=baseline, registry=CommandRegistry(definitions=definitions), working_directory_aliases={"BASELINE_SANDBOX": baseline}, runtime_profiles=frozenset({runtime_profile_id}), network_profiles=frozenset({"approved-registries-only"}), environment_overrides=environment_overrides or {}); return ExecutionWorker(policy, CommandLogWriter(store, max_output_bytes=None))

    def _runtime_environment(self, run_id, profile_id, checksum):
        with self._scope() as session:
            profile = self._profile(session, run_id, profile_id, checksum)
            selected = next((item for item in (profile.profiles or []) if item.get("profile_id") == profile.selected_profile_id and item.get("checksum") == profile.selected_checksum), None) if profile else None
        if not selected:
            return {}
        directories = []
        for executable in (selected.get("node_executable"), selected.get("package_manager_executable"), selected.get("npx_executable")):
            if executable:
                directory = str(Path(executable).parent)
                if directory not in directories:
                    directories.append(directory)
        current_path = os.environ.get("PATH", "")
        return {"PATH": os.pathsep.join([*directories, current_path]) if current_path else os.pathsep.join(directories)}

    def _run_by_id(self, run_id):
        with self._scope() as session: return self._run(session, run_id)
    @staticmethod
    def _run(session, run_id):
        run=session.get(MigrationRunModel, run_id)
        if run is None: raise BaselineInstallApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        return run
    @staticmethod
    def _baseline(session, run_id): return session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == run_id).order_by(BaselineQualificationModel.created_at.desc()))
    @staticmethod
    def _profile(session, run_id, profile_id, checksum):
        record=session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.created_at.desc())); return record if record is not None and record.selected_profile_id == profile_id and record.selected_checksum == checksum else None
    @staticmethod
    def _existing(session, run_id, key): return session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id, CommandExecutionModel.idempotency_key == key))
    def _transition(self, session, run, request, event_type, reason, payload, *, expected_state_version=None):
        try: return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=run.state_version if expected_state_version is None else expected_state_version, idempotency_key=request.idempotency_key + ":" + event_type.value + ":" + uuid4().hex, event_type=event_type, actor=request.actor, reason=reason, occurred_at=self._now(), payload=payload))
        except StaleStateVersionError as error: raise BaselineInstallApplicationError("STALE_STATE_VERSION", str(error), 409) from error
    @staticmethod
    @staticmethod
    def _redact(value: str) -> str:
        return re.sub(r"(?i)(token|password|secret|authorization|npm_config_\\w+)\\s*[:=]\\s*[^\\s]+", r"\\1=[REDACTED]", value)

    @staticmethod
    def _response(record, *, idempotent_replay=False):
        return BaselineInstallResponse(run_id=record.run_id, execution_id=record.id, command_id=record.command_id, status=record.status, exit_code=record.exit_code, started_at=record.started_at.isoformat() if record.started_at else None, finished_at=record.finished_at.isoformat() if record.finished_at else None, duration_ms=record.duration_ms, timed_out=record.timed_out, cancelled=record.cancelled, reconstruction_required=record.reconstruction_required, runtime_checksum=record.runtime_checksum, baseline_checksum=record.baseline_checksum, start_fingerprint=record.start_fingerprint, end_fingerprint=record.end_fingerprint, blockers=record.blockers or [], artifact_ids=record.artifact_ids or [], state_version=record.state_version, event_sequence=record.event_sequence, idempotent_replay=idempotent_replay)
