"""Application service for the S1-F12 baseline build/test/lint matrix."""
from __future__ import annotations
import hashlib
import json
import os
import re
import threading
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import func, select
from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandDefinition, CommandPolicy, CommandRegistry, ExecutionWorker
from app.command_execution.worker import CommandLogWriter
from app.domain.baseline_matrix import BaselineTargetDiscoveryService, BaselineTargetInventory, BaselineTargetKind, BaselineTargetResult, BaselineTargetStatus, normalize_command_result
from app.domain.contracts import ArtifactType, CancellationPolicy, CommandRequestDto, WorkflowEventType
from app.repositories.models import ArtifactMetadataModel, BaselineQualificationModel, BaselineValidationModel, CommandExecutionModel, ExecutionProfileModel, MigrationRunModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.state.transition_service import StaleStateVersionError, StateTransitionService, TransitionRequest
class BaselineValidationApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message); self.code, self.message, self.status_code = code, message, status_code
class BaselineValidationApplicationService:
    _ACTIVE: dict[tuple[str, str], threading.Event] = {}
    _EVENTS = {"build": (WorkflowEventType.BASELINE_BUILD_STARTED, WorkflowEventType.BASELINE_BUILD_COMPLETED), "test": (WorkflowEventType.BASELINE_TESTS_STARTED, WorkflowEventType.BASELINE_TESTS_COMPLETED), "lint": (WorkflowEventType.BASELINE_LINT_STARTED, WorkflowEventType.BASELINE_LINT_COMPLETED)}
    def __init__(self, *, scope=session_scope, discovery=None, now_provider=None):
        self._scope = scope; self._discovery = discovery or BaselineTargetDiscoveryService(); self._now = now_provider or (lambda: datetime.now(UTC))
    def get_targets(self, run_id: str):
        with self._scope() as session:
            run, baseline = self._run_and_baseline(session, run_id); inventory = self._discover(baseline)
            from app.api.baseline_matrix_contracts import BaselineTargetInventoryResponse
            return BaselineTargetInventoryResponse(run_id=run_id, targets=[self._target_dict(t) for t in inventory.targets], package_json_checksum=inventory.package_json_checksum, angular_json_present=inventory.angular_json_present, state_version=run.state_version, event_sequence=self._latest_sequence(session, run_id))
    def get(self, run_id: str, kind: str):
        self._validate_kind(kind)
        with self._scope() as session:
            record = session.scalar(select(BaselineValidationModel).where(BaselineValidationModel.run_id == run_id, BaselineValidationModel.kind == kind).order_by(BaselineValidationModel.created_at.desc()))
            return self._response(record) if record else None
    def cancel(self, run_id: str, kind: str):
        self._validate_kind(kind)
        event = self._ACTIVE.get((run_id, kind))
        if event is not None:
            event.set()
        result = self.get(run_id, kind)
        if result is None:
            raise BaselineValidationApplicationError("BASELINE_VALIDATION_NOT_FOUND", "Baseline validation was not found.", 404)
        return result

    def execute(self, run_id: str, kind: str, request):
        self._validate_kind(kind)
        with self._scope() as session:
            run, baseline = self._run_and_baseline(session, run_id)
            replay = session.scalar(select(BaselineValidationModel).where(BaselineValidationModel.run_id == run_id, BaselineValidationModel.idempotency_key == request.idempotency_key))
            if replay: return self._response(replay, replay=True)
            self._require_prerequisites(session, run, baseline, request.prerequisite_artifact_ids); self._require_state(run, request.expected_state_version)
            inventory = self._discover(baseline); targets = [t for t in inventory.targets if t.kind.value == kind]
            if not targets: raise BaselineValidationApplicationError("BASELINE_TARGETS_NOT_FOUND", f"No {kind} baseline targets were discovered.", 409)
            self._transition(session, run, request, WorkflowEventType.BASELINE_TARGETS_DISCOVERED, "baseline validation targets discovered", {"kind": kind, "target_count": len(targets), "package_json_checksum": inventory.package_json_checksum})
            started = self._transition(session, run, request, self._EVENTS[kind][0], f"baseline {kind} validation started", {"kind": kind, "target_count": len(targets)})
            validation = BaselineValidationModel(id=f"validation-{uuid4().hex[:12]}", run_id=run_id, idempotency_key=request.idempotency_key, actor=request.actor, kind=kind, status="running", targets=[self._target_dict(t) for t in targets], results=[], parser_summary=None, artifact_ids=[], artifact_checksums={}, prerequisite_artifact_ids=list(request.prerequisite_artifact_ids), baseline_checksum=baseline.checksum, state_version=started.next_state_version, event_sequence=started.event_sequence, created_at=self._now(), updated_at=self._now())
            session.add(validation); session.flush(); sandbox = Path(baseline.sandbox_path); profile = self._profile(session, run_id); runtime_id = profile.selected_profile_id if profile and profile.selected_profile_id else "source-runtime-profile"; runtime_checksum = profile.selected_checksum if profile else None
            bound_targets = [self._bind_runtime_target(target, profile) for target in targets]
            validation.targets = [self._target_dict(target) for target in bound_targets]
            definitions = tuple(CommandDefinition(t.command_id, t.executable, t.arguments) for t in bound_targets if t.supported); worker = self._worker(run, sandbox, definitions, runtime_id, self._runtime_environment(profile))
            targets = bound_targets
        cancel_event = threading.Event(); self._ACTIVE[(run_id, kind)] = cancel_event
        results: list[BaselineTargetResult] = []; executed: list[tuple[BaselineTargetResult, object, CommandRequestDto]] = []
        output_sequence = 0
        execution_error: Exception | None = None
        try:
            for index, target in enumerate(targets):
                if cancel_event.is_set():
                    results.extend(normalize_command_result(later, exit_code=None, duration_ms=None, cancelled=True) for later in targets[index:])
                    break
                if not target.supported:
                    results.append(normalize_command_result(target, exit_code=None, duration_ms=None)); continue
                command_request = CommandRequestDto(command_id=target.command_id, run_id=run_id, executable=target.executable, arguments=list(target.arguments), shell=False, working_directory_alias=target.working_directory_alias, runtime_profile_id=runtime_id, timeout_seconds=3600, network_profile="none", cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE, idempotency_key=f"{request.idempotency_key}:{target.target_id}", requested_by=request.actor, requester=request.actor, requested_at=self._now())
                try:
                    def output_callback(stream, chunk):
                        nonlocal output_sequence
                        output_sequence += 1
                        self._persist_output_chunk(run_id, request, kind, target.command_id, stream, chunk, output_sequence)
                    execution = worker.run(command_request, cancel_event=cancel_event, output_callback=output_callback); output = self._execution_output(execution, run_id)
                except Exception as error:
                    execution_error = error
                    failed = normalize_command_result(target, exit_code=None, duration_ms=None, warnings=(str(error),), failed_tests=())
                    results.append(replace(failed, blocker="EXECUTION_ERROR"))
                    results.extend(replace(normalize_command_result(later, exit_code=None, duration_ms=None), status=BaselineTargetStatus.BLOCKED, blocker="PREVIOUS_TARGET_EXECUTION_FAILED") for later in targets[index + 1:])
                    break
                result = normalize_command_result(target, exit_code=execution.result.exit_code, duration_ms=execution.result.duration_ms, cancelled=execution.cancelled, interrupted=execution.timed_out, warnings=self._warnings(output), test_count=self._test_count(output), failed_tests=self._failed_tests(output))
                result = replace(result, output_location=execution.command_log_artifact.ref.relative_path, artifact_ids=tuple(ref.artifact_id for ref in [execution.command_log_artifact.ref, execution.stdout_artifact.ref if execution.stdout_artifact else None, execution.stderr_artifact.ref if execution.stderr_artifact else None] if ref)); results.append(result); executed.append((result, execution, command_request))
        finally:
            self._ACTIVE.pop((run_id, kind), None)
        with self._scope() as session:
            run, baseline = self._run_and_baseline(session, run_id); record = session.get(BaselineValidationModel, validation.id)
            if record is None: raise BaselineValidationApplicationError("BASELINE_VALIDATION_NOT_FOUND", "Validation record disappeared.", 500)
            result_dicts = [self._result_dict(r) for r in results]; artifact_ids = [self._write_target_inventory(session, run, inventory)]
            for result, execution, command_request in executed:
                command = CommandExecutionModel(id=f"execution-{uuid4().hex[:12]}", run_id=run_id, stage_id=None, idempotency_key=command_request.idempotency_key, requested_by=request.actor, requester=request.actor, command_id=command_request.command_id, executable=command_request.executable, arguments=list(command_request.arguments), shell=False, working_directory_alias=command_request.working_directory_alias, runtime_profile_id=runtime_id, runtime_checksum=runtime_checksum, baseline_checksum=baseline.checksum, status=execution.result.status.value, requested_at=command_request.requested_at, started_at=execution.result.started_at, finished_at=execution.result.finished_at, exit_code=execution.result.exit_code, duration_ms=execution.result.duration_ms, timed_out=execution.timed_out, cancelled=execution.cancelled, stdout_artifact_id=execution.stdout_artifact.ref.artifact_id if execution.stdout_artifact else None, stderr_artifact_id=execution.stderr_artifact.ref.artifact_id if execution.stderr_artifact else None, command_log_artifact_id=execution.command_log_artifact.ref.artifact_id, artifact_ids=[], blockers=[], state_version=record.state_version, event_sequence=record.event_sequence)
                command.artifact_ids = [ref.artifact_id for ref in [execution.command_log_artifact.ref, execution.stdout_artifact.ref if execution.stdout_artifact else None, execution.stderr_artifact.ref if execution.stderr_artifact else None] if ref]
                for artifact_id in command.artifact_ids: self._register_artifact(session, run, artifact_id)
                artifact_ids.extend(command.artifact_ids); session.add(command)
            summary = self._summary(results); report_id = self._write_report(session, run, kind, targets, result_dicts, summary, request.idempotency_key); artifact_ids.append(report_id)
            if kind == "build": artifact_ids.append(self._write_generated_output_inventory(session, run, baseline))
            status = "blocked" if any(r.status is BaselineTargetStatus.BLOCKED for r in results) and not any(r.status is BaselineTargetStatus.FAILED for r in results) else "failed" if execution_error is not None or any(r.status in {BaselineTargetStatus.FAILED, BaselineTargetStatus.CANCELLED, BaselineTargetStatus.INTERRUPTED} for r in results) else results[0].status.value if results and all(r.status is results[0].status for r in results) and results[0].status in {BaselineTargetStatus.SKIPPED_NOT_CONFIGURED, BaselineTargetStatus.SKIPPED_NOT_APPLICABLE} else "passed"
            completed = self._transition(session, run, request, self._EVENTS[kind][1], f"baseline {kind} validation completed", {"kind": kind, "status": status, "artifact_count": len(artifact_ids)}, expected_state_version=run.state_version)
            record.status, record.results, record.parser_summary, record.artifact_ids = status, result_dicts, summary, artifact_ids; record.artifact_checksums = {artifact_id: self._artifact_checksum(run, artifact_id) for artifact_id in artifact_ids}; record.state_version, record.event_sequence, record.updated_at = completed.next_state_version, completed.event_sequence, self._now(); session.flush(); self._ACTIVE.pop((run_id, kind), None); return self._response(record)
    def _worker(self, run, sandbox, definitions, runtime_id, environment_overrides=None):
        root = Path(run.artifact_root).resolve(); store = LocalFilesystemArtifactStore(root, fixed_run_root=root); policy = CommandPolicy(sandbox_root=sandbox, registry=CommandRegistry(definitions=definitions), working_directory_aliases={"BASELINE_SANDBOX": sandbox}, runtime_profiles=frozenset({runtime_id}), network_profiles=frozenset({"none"}), environment_overrides=environment_overrides or {}); return ExecutionWorker(policy, CommandLogWriter(store), timeout_seconds=3600)
    @staticmethod
    def _runtime_environment(profile):
        if profile is None:
            return {}
        selected = next((item for item in (profile.profiles or []) if item.get("profile_id") == profile.selected_profile_id and item.get("checksum") == profile.selected_checksum), None)
        if selected is None:
            return {}
        executables = [selected.get("node_executable"), selected.get("package_manager_executable"), selected.get("npx_executable")]
        directories = []
        for executable in executables:
            if executable:
                directory = str(Path(executable).parent)
                if directory not in directories:
                    directories.append(directory)
        current_path = os.environ.get("PATH", "")
        environment = {"PATH": os.pathsep.join([*directories, current_path]) if current_path else os.pathsep.join(directories)}
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin and Path(chrome_bin).is_file():
            environment["CHROME_BIN"] = str(Path(chrome_bin).resolve())
        return environment
    @staticmethod
    def _bind_runtime_target(target, profile):
        """Replace PATH-resolved npm/npx shims with the selected profile paths."""
        if profile is None:
            return target
        selected = next((item for item in (profile.profiles or []) if item.get("profile_id") == profile.selected_profile_id and item.get("checksum") == profile.selected_checksum), None)
        if selected is None:
            return target
        executable = target.executable
        if executable in {"npm", "npm.cmd"}:
            executable = selected.get("package_manager_executable") or executable
        elif executable in {"npx", "npx.cmd"}:
            executable = selected.get("npx_executable") or executable
        return replace(target, executable=executable)
    def _discover(self, baseline):
        try: return self._discovery.discover(Path(baseline.sandbox_path))
        except (OSError, ValueError) as error: raise BaselineValidationApplicationError("BASELINE_TARGET_DISCOVERY_FAILED", str(error), 422) from error
    def _run_and_baseline(self, session, run_id):
        run = session.get(MigrationRunModel, run_id); baseline = session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == run_id).order_by(BaselineQualificationModel.created_at.desc()))
        if run is None: raise BaselineValidationApplicationError("RUN_NOT_FOUND", "Migration run was not found.", 404)
        if baseline is None: raise BaselineValidationApplicationError("BASELINE_WORKSPACE_REQUIRED", "Baseline qualification is required.", 409)
        return run, baseline
    @staticmethod
    def _require_prerequisites(session, run, baseline, artifact_ids):
        if baseline.authorization_status != "authorized" or baseline.blockers: raise BaselineValidationApplicationError("BASELINE_INSTALL_AUTHORIZATION_REQUIRED", "An authorized clean baseline is required.", 409)
        if artifact_ids:
            found = {row.id.removeprefix("metadata-") for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run.id)).all()}; missing = [item for item in artifact_ids if item not in found]
            if missing: raise BaselineValidationApplicationError("PREREQUISITE_ARTIFACT_NOT_FOUND", "A prerequisite artifact is not registered.", 409)
    def _transition(self, session, run, request, event_type, reason, payload, expected_state_version=None):
        try: return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=run.state_version if expected_state_version is None else expected_state_version, idempotency_key=f"{request.idempotency_key}:{event_type.value}", event_type=event_type, actor=request.actor, reason=reason, occurred_at=self._now(), payload=payload))
        except StaleStateVersionError as error: raise BaselineValidationApplicationError("STALE_STATE_VERSION", str(error), 409) from error
    @staticmethod
    def _require_state(run, expected):
        if run.state_version != expected: raise BaselineValidationApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)
    @staticmethod
    def _profile(session, run_id): return session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))
    @staticmethod
    def _validate_kind(kind):
        if kind not in {"build", "test", "lint"}: raise BaselineValidationApplicationError("BASELINE_KIND_INVALID", "Validation kind must be build, test, or lint.", 422)
    @staticmethod
    def _latest_sequence(session, run_id): return int(session.scalar(select(func.max(WorkflowEventModel.sequence)).where(WorkflowEventModel.run_id == run_id)) or 0)
    @staticmethod
    def _target_dict(target): return {"target_id": target.target_id, "kind": target.kind.value, "project": target.project, "configuration": target.configuration, "command_id": target.command_id, "executable": target.executable, "arguments": list(target.arguments), "supported": target.supported, "blocker": target.blocker, "builder": target.builder, "canonical_target_id": target.canonical_target_id, "support_reason": target.support_reason}
    @staticmethod
    def _result_dict(result): return {"target_id": result.target_id, "kind": result.kind.value, "status": result.status.value, "exit_code": result.exit_code, "duration_ms": result.duration_ms, "warnings": list(result.warnings), "test_count": result.test_count, "failed_tests": list(result.failed_tests), "output_location": result.output_location, "artifact_ids": list(result.artifact_ids), "blocker": result.blocker}
    @staticmethod
    def _response(record, replay=False):
        from app.api.baseline_matrix_contracts import BaselineValidationResponse
        return BaselineValidationResponse(validation_id=record.id, run_id=record.run_id, kind=record.kind, status=record.status, targets=record.targets or [], results=record.results or [], parser_summary=record.parser_summary, artifact_ids=record.artifact_ids or [], artifact_checksums=record.artifact_checksums or {}, baseline_checksum=record.baseline_checksum, state_version=record.state_version, event_sequence=record.event_sequence, idempotent_replay=replay)
    def _execution_output(self, execution, run_id):
        root = Path(self._run_root(run_id)).resolve(); store = LocalFilesystemArtifactStore(root, fixed_run_root=root); values = []
        for artifact in (execution.stdout_artifact, execution.stderr_artifact):
            if artifact: values.append(store.read_artifact(run_id, artifact.ref.relative_path).content)
        return "\n".join(values)
    def _persist_output_chunk(self, run_id, request, kind, command_id, stream, chunk, sequence):
        safe = self._redact_live_output(chunk)
        if not safe:
            return
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                return
            transition = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=run.state_version, idempotency_key=f"{request.idempotency_key}:output:{sequence}", event_type=WorkflowEventType.COMMAND_OUTPUT_CHUNK, actor=request.actor, reason="baseline validation command output chunk", occurred_at=self._now(), payload={"kind": kind, "command_id": command_id, "stream": stream, "chunk": safe, "sequence": sequence}))
            session.flush()
    def _run_root(self, run_id):
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None or not run.artifact_root: raise BaselineValidationApplicationError("ARTIFACT_ROOT_REQUIRED", "Run artifact root is required.", 409)
            return run.artifact_root
    @staticmethod
    def _warnings(output): return tuple(line.strip() for line in output.splitlines() if "warning" in line.lower())
    @staticmethod
    def _redact_live_output(value: str, limit: int = 64_000) -> str:
        redacted = re.sub(r"(?i)((?:token|password|secret|authorization|api[_-]?key|npm_config_\w+)\s*(?:=|:)\s*)(?:Bearer\s+)?([^\s'\"]+)", r"\1[REDACTED]", value)
        encoded = redacted.encode("utf-8")
        if len(encoded) <= limit:
            return redacted
        suffix = "\n[output chunk truncated]"
        return encoded[:max(0, limit - len(suffix.encode("utf-8")))].decode("utf-8", errors="replace") + suffix
    @staticmethod
    def _test_count(output):
        match = re.search(r"^\s*Tests:\s+(\d+)\s+(?:passed|failed)", output, re.IGNORECASE | re.MULTILINE)
        if match is None:
            match = re.search(r"(\d+)\s+(?:tests?\s+)?(?:passed|failed)", output, re.IGNORECASE)
        return int(match.group(1)) if match else None
    @staticmethod
    def _failed_tests(output): return tuple(line.strip() for line in output.splitlines() if "fail" in line.lower())
    @staticmethod
    def _summary(results): return {"target_count": len(results), "passed": sum(r.status is BaselineTargetStatus.PASSED for r in results), "failed": sum(r.status is BaselineTargetStatus.FAILED for r in results), "blocked": sum(r.status is BaselineTargetStatus.BLOCKED for r in results), "skipped_not_configured": sum(r.status is BaselineTargetStatus.SKIPPED_NOT_CONFIGURED for r in results), "skipped_not_applicable": sum(r.status is BaselineTargetStatus.SKIPPED_NOT_APPLICABLE for r in results), "cancelled": sum(r.status is BaselineTargetStatus.CANCELLED for r in results), "interrupted": sum(r.status is BaselineTargetStatus.INTERRUPTED for r in results)}
    def _write_target_inventory(self, session, run, inventory):
        payload = {"run_id": run.id, "package_json_checksum": inventory.package_json_checksum, "angular_json_present": inventory.angular_json_present, "targets": [self._target_dict(target) for target in inventory.targets]}
        store = LocalFilesystemArtifactStore(Path(run.artifact_root).resolve(), fixed_run_root=Path(run.artifact_root).resolve())
        stored = store.write_text_artifact(run.id, "01_baseline/baseline_target_inventory.json", json.dumps(payload, indent=2, sort_keys=True), ArtifactType.JSON, created_by="baseline-validation-service", created_at=self._now(), policy_version="baseline-validation-v1")
        self._register_artifact(session, run, stored.ref.artifact_id)
        return stored.ref.artifact_id

    def _write_generated_output_inventory(self, session, run, baseline):
        sandbox = Path(baseline.sandbox_path).resolve()
        files = []
        if sandbox.is_dir():
            for path in sorted(item for item in sandbox.rglob("*") if item.is_file() and ".git" not in item.parts):
                relative = path.relative_to(sandbox).as_posix()
                files.append({"path": relative, "size_bytes": path.stat().st_size, "checksum": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()})
        payload = {"run_id": run.id, "sandbox_path": str(sandbox), "files": files}
        store = LocalFilesystemArtifactStore(Path(run.artifact_root).resolve(), fixed_run_root=Path(run.artifact_root).resolve())
        stored = store.write_text_artifact(run.id, "01_baseline/generated_output_inventory.json", json.dumps(payload, indent=2, sort_keys=True), ArtifactType.JSON, created_by="baseline-validation-service", created_at=self._now(), policy_version="baseline-validation-v1")
        self._register_artifact(session, run, stored.ref.artifact_id)
        return stored.ref.artifact_id

    @staticmethod
    def _artifact_checksum(run, artifact_id):
        root = Path(run.artifact_root).resolve()
        return LocalFilesystemArtifactStore(root, fixed_run_root=root).read_artifact_by_id(artifact_id).ref.checksum

    def _write_report(self, session, run, kind, targets, results, summary, idempotency_key):
        root = Path(run.artifact_root).resolve(); store = LocalFilesystemArtifactStore(root, fixed_run_root=root); stored = store.write_text_artifact(run.id, f"01_baseline/baseline_{kind}_report.json", json.dumps({"kind": kind, "targets": [self._target_dict(t) for t in targets], "results": results, "summary": summary}, indent=2, sort_keys=True), ArtifactType.JSON, created_by="baseline-validation-service", created_at=self._now(), input_hashes={"request": idempotency_key}, policy_version="baseline-validation-v1"); self._register_artifact(session, run, stored.ref.artifact_id); return stored.ref.artifact_id
    @staticmethod
    def _register_artifact(session, run, artifact_id):
        if session.get(ArtifactMetadataModel, f"metadata-{artifact_id}") is None:
            root = Path(run.artifact_root).resolve(); stored = LocalFilesystemArtifactStore(root, fixed_run_root=root).read_artifact_by_id(artifact_id); session.add(ArtifactMetadataModel(id=f"metadata-{artifact_id}", run_id=run.id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=stored.ref.created_at))
