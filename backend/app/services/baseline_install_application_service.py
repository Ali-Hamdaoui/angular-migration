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
from app.command_execution import CommandLogWriter, CommandPolicy, ExecutionWorker
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

    def __init__(self, *, session_scope_factory=session_scope, worker_factory=None, now_provider=None) -> None:
        self._scope = session_scope_factory; self._worker_factory = worker_factory; self._now = now_provider or (lambda: datetime.now(UTC))
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
            command = FrozenBaselineCommandPolicy().create()
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
            worker = self._worker(self._run_by_id(run_id), request.runtime_profile_id)
            command_request = command.request(run_id=run_id, runtime_profile_id=request.runtime_profile_id, timeout_seconds=request.timeout_seconds, idempotency_key=request.idempotency_key, actor=request.actor, requested_at=self._now())
            result = BaselineInstallationService(worker).execute(command_request, sandbox=sandbox, prerequisites=BaselineInstallPrerequisites(True, True, True, True, True), cancel_event=cancel_event, output_callback=lambda stream, chunk: self._output_chunk(run_id, execution_id, request, stream, chunk))
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
        jobs = []
        recovered = 0
        with self._scope() as session:
            records = session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.status.in_([CommandStatus.PENDING.value, CommandStatus.RUNNING.value]))).all()
            for record in records:
                run = self._run(session, record.run_id)
                aliases = run.workspace_aliases or {}
                sandbox = Path(aliases.get("BASELINE_SANDBOX", ""))
                current = FrozenBaselineInspectionService().inspect_before(sandbox) if sandbox.is_dir() else None
                fingerprints = record.start_fingerprint or {}
                safe_to_rerun = bool(current and current[0].checksum == (fingerprints.get("package_json") or {}).get("checksum") and current[1].checksum == (fingerprints.get("lockfile") or {}).get("checksum"))
                request = BaselineInstallRequest(expected_state_version=record.state_version, idempotency_key=record.idempotency_key or f"supervisor-recovery:{record.id}", actor="baseline-supervisor", runtime_profile_id=record.runtime_profile_id or "unknown", runtime_checksum=record.runtime_checksum or "unknown", timeout_seconds=record.timeout_seconds or 3600)
                action = "rerun" if safe_to_rerun else "reconstruct"
                reconstruction = self._reconstruct_baseline(session, run, record.id) if not safe_to_rerun else {"status": "not_required"}
                try:
                    completed = self._transition(session, run, request, WorkflowEventType.COMMAND_INTERRUPTED, "worker lease was lost during restart recovery", {"execution_id": record.id, "worker_id": record.worker_id, "recovery_action": action, "reconstruction_required": not safe_to_rerun}, expected_state_version=run.state_version)
                except BaselineInstallApplicationError:
                    continue
                record.status = CommandStatus.PENDING.value if safe_to_rerun else CommandStatus.FAILED.value
                record.finished_at = None if safe_to_rerun else self._now()
                record.cancelled = False
                record.reconstruction_required = not safe_to_rerun
                record.blockers = ["WORKER_LOST_SAFE_TO_RERUN"] if safe_to_rerun else (["BASELINE_RECONSTRUCTED"] if reconstruction.get("status") == "reconstructed" else [reconstruction.get("blocker", "BASELINE_RECONSTRUCTION_FAILED")])
                record.state_version = completed.next_state_version
                record.event_sequence = completed.event_sequence
                for lease in session.scalars(select(WorkerLeaseModel).where(WorkerLeaseModel.execution_id == record.id)).all(): session.delete(lease)
                if safe_to_rerun and current is not None: jobs.append((record.run_id, record.id, request, sandbox, current, FrozenBaselineCommandPolicy().create()))
                recovered += 1
            session.flush()
        for run_id, execution_id, request, sandbox, before, command in jobs:
            cancel_event = threading.Event()
            with self._lock:
                self._cancel_events[execution_id] = cancel_event
                self._output_buffers[execution_id] = {"stdout": [], "stderr": []}
            self._executor.submit(self._execute, run_id, execution_id, request, sandbox, before, command, cancel_event)
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
            artifacts = self._persist_artifacts(session, run, result, request, execution_id, reconstruction)
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
        artifacts = [
            self._write_artifact(store, run, "04_workflow_state/command_logs/npm-ci-bootstrap-failure.json", json.dumps({"command_id": "npm-ci-bootstrap", "status": "FAILED", "blocker": blocker, "environment_blocker": environment_blocker, "detail": detail}, indent=2), ArtifactType.COMMAND_LOG, request),
            self._write_artifact(store, run, "04_workflow_state/command_logs/npm-ci-bootstrap-failure.stdout.log", "".join(buffers.get("stdout", [])), ArtifactType.TEXT_LOG, request),
            self._write_artifact(store, run, "04_workflow_state/command_logs/npm-ci-bootstrap-failure.stderr.log", "".join(buffers.get("stderr", [])), ArtifactType.TEXT_LOG, request),
            self._write_artifact(store, run, "01_baseline/lockfile_post_install_verification.json", json.dumps({"package_json": asdict(after[0]), "lockfile": asdict(after[1]), "unchanged": after == before}, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/baseline_install_summary.json", json.dumps({"status": "failed", "blockers": [blocker], "reconstruction": reconstruction}, indent=2, default=str), ArtifactType.JSON, request),
        ]
        self._register_artifacts(session, run, artifacts)
        return [a.ref.artifact_id for a in artifacts]

    @staticmethod
    def _npm_debug_log_paths(run, result):
        aliases = run.workspace_aliases or {}
        candidates = []
        sandbox = Path(aliases.get("BASELINE_SANDBOX", ""))
        if sandbox.is_dir(): candidates.extend(sandbox.glob("npm-debug.log*"))
        configured = {os.environ.get("npm_config_cache"), os.environ.get("NPM_CONFIG_CACHE"), str(Path.home() / "AppData" / "Local" / "npm-cache"), str(Path.home() / "AppData" / "Roaming" / "npm-cache")}
        for value in configured:
            if value: candidates.extend(Path(value).expanduser().glob("_logs/*.log"))
        started = result.command.result.started_at.timestamp(); finished = (result.command.result.finished_at or datetime.now(UTC)).timestamp(); unique = {}
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                if resolved.is_file() and started - 1 <= resolved.stat().st_mtime <= finished + 1: unique[str(resolved)] = resolved
            except OSError: continue
        return tuple(unique.values())

    @staticmethod
    def _register_artifacts(session, run, artifacts):
        for artifact in artifacts:
            session.add(ArtifactMetadataModel(id=f"metadata-{artifact.ref.artifact_id}", run_id=run.id, stage_id=None, artifact_type=artifact.ref.artifact_type.value, relative_path=artifact.ref.relative_path, checksum=artifact.ref.checksum, created_at=artifact.ref.created_at))
    def _persist_artifacts(self, session, run, result, request, execution_id, reconstruction):
        root = Path(run.artifact_root).resolve()
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        artifacts = [result.command.command_log_artifact]
        if result.command.stdout_artifact: artifacts.append(result.command.stdout_artifact)
        if result.command.stderr_artifact: artifacts.append(result.command.stderr_artifact)
        artifacts.extend([
            self._write_artifact(store, run, "01_baseline/npm-ci-command.json", json.dumps({"command_id": "npm-ci-bootstrap", "executable": "npm", "arguments": ["ci"], "runtime_profile_id": request.runtime_profile_id, "runtime_checksum": request.runtime_checksum}, indent=2), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/dependency_tree_verification.json", json.dumps(asdict(result.inspection.dependency_tree) if result.inspection.dependency_tree else {"status": "not_run"}, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/lockfile_post_install_verification.json", json.dumps({"package_json": asdict(result.inspection.package_json), "lockfile": asdict(result.inspection.lockfile), "unchanged": not result.inspection.blockers}, indent=2, default=str), ArtifactType.JSON, request),
            self._write_artifact(store, run, "01_baseline/baseline_install_summary.json", json.dumps({"status": result.inspection.status, "blockers": list(result.inspection.blockers), "reconstruction": reconstruction}, indent=2, default=str), ArtifactType.JSON, request),
        ])
        for index, debug_path in enumerate(self._npm_debug_log_paths(run, result)):
            try:
                artifacts.append(self._write_artifact(store, run, f"01_baseline/npm-debug/{index:03d}-{debug_path.name}", self._redact(debug_path.read_text(encoding="utf-8", errors="replace")), ArtifactType.TEXT_LOG, request))
            except OSError:
                continue
        self._register_artifacts(session, run, artifacts)
        with self._lock: self._output_buffers.pop(execution_id, None)
        return [a.ref.artifact_id for a in artifacts]
    def _worker(self, run, runtime_profile_id):
        if self._worker_factory is not None: return self._worker_factory(run)
        baseline = Path((run.workspace_aliases or {})["BASELINE_SANDBOX"]).resolve(); root = Path(run.artifact_root).resolve(); store = LocalFilesystemArtifactStore(root, fixed_run_root=root); policy = CommandPolicy(sandbox_root=baseline, working_directory_aliases={"BASELINE_SANDBOX": baseline}, runtime_profiles=frozenset({runtime_profile_id}), network_profiles=frozenset({"approved-registries-only"})); return ExecutionWorker(policy, CommandLogWriter(store, max_output_bytes=None))

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
