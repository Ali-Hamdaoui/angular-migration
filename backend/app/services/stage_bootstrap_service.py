"""Authoritative stage bootstrap clean-install application service (AMFA-145)."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.stage_contracts import StageBootstrapInstallResponse, StageBootstrapStatusResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandLogWriter, CommandPolicy, CommandRegistry, ExecutionWorker
from app.domain.contracts import ArtifactType, CancellationPolicy, CommandRequestDto, CommandStatus, WorkflowEventType
from app.domain.stage_workspace import StageExecutionPlan
from app.repositories.models import ArtifactMetadataModel, CommandExecutionModel, ExecutionProfileModel, MigrationRunModel
from app.repositories.models.workflow import MigrationStageModel, StageStepModel
from app.repositories.session import session_scope
from app.repositories.stage_workspace_models import G07ApprovalModel, StageWorkspaceModel
from app.state.transition_service import StateTransitionService, TransitionRequest

_APPROVED_LIFECYCLE_STATUSES = frozenset({"approved", "approved_with_comment"})


class StageApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.status_code = status_code


class StageBootstrapApplicationService:
    """Execute the locked bootstrap command only in the approved stage sandbox."""

    STAGE_POLICY_VERSION = "stage-bootstrap-install-v1"
    STEP_NAME = "bootstrap_install"
    APPROVED_COMMAND_ID = "npm-ci-bootstrap"
    WORKING_DIRECTORY_ALIAS = "STAGE_SANDBOX"
    NETWORK_PROFILE = "approved-registries-only"
    TIMEOUT_SECONDS = 600

    def __init__(self, *, session_scope_factory=session_scope, worker_factory=None, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._worker_factory = worker_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def run_bootstrap_install(self, run_id: str, stage_id: str, request) -> StageBootstrapInstallResponse:
        prepared = self._prepare(run_id, stage_id, request)
        if isinstance(prepared, StageBootstrapInstallResponse):
            return prepared
        execution_id, sandbox, profile_id, pre_fingerprint, workspace_id, g07_id = prepared
        return self._execute(run_id, stage_id, execution_id, sandbox, profile_id, pre_fingerprint, workspace_id, g07_id, request)

    def _prepare(self, run_id: str, stage_id: str, request):
        now = self._now()
        with self._scope() as session:
            run = self._run(session, run_id)
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None or stage.run_id != run_id:
                raise StageApplicationError("STAGE_NOT_FOUND", "Stage does not exist for this run.", status_code=404)

            existing = session.scalar(select(CommandExecutionModel).where(
                CommandExecutionModel.run_id == run_id,
                CommandExecutionModel.idempotency_key == request.idempotency_key,
            ))
            if existing is not None:
                if existing.stage_id != stage_id or existing.command_id != self.APPROVED_COMMAND_ID:
                    raise StageApplicationError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key is bound to another request.", status_code=409)
                return self._response(session, existing, idempotent_replay=True)

            if run.state_version != request.expected_state_version:
                raise StageApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            workspace = session.scalar(select(StageWorkspaceModel).where(
                StageWorkspaceModel.run_id == run_id, StageWorkspaceModel.stage_id == stage_id
            ).order_by(StageWorkspaceModel.created_at.desc()))
            if workspace is None:
                raise StageApplicationError("STAGE_SANDBOX_MISSING", "The stage sandbox has not been prepared.", status_code=409)
            if workspace.copy_status not in {"completed", "ready", "verified"}:
                raise StageApplicationError("STAGE_SANDBOX_STALE", "The stage sandbox is not ready.", status_code=409)

            sandbox = self._authorized_sandbox(run, workspace)
            g07 = session.scalar(select(G07ApprovalModel).where(
                G07ApprovalModel.run_id == run_id, G07ApprovalModel.stage_id == stage_id
            ).order_by(G07ApprovalModel.created_at.desc(), G07ApprovalModel.id.desc()))
            if g07 is None:
                raise StageApplicationError("MISSING_G07_AUTHORIZATION", "G07 authorization is required.", status_code=409)
            if g07.status not in {"approved", "approved_with_comment"}:
                raise StageApplicationError("MISSING_G07_AUTHORIZATION", "G07 is not approved.", status_code=409)
            if g07.package.get("workspace_fingerprint") != workspace.workspace_fingerprint:
                raise StageApplicationError("STALE_G07_DECISION", "The G07 decision is stale for the current workspace.", status_code=409)

            plan_payload = ((g07.package or {}).get("input_manifest") or {}).get("plan")
            if not plan_payload:
                raise StageApplicationError("STAGE_PLAN_MISSING", "The locked stage execution plan is missing.", status_code=409)
            plan = StageExecutionPlan.model_validate(plan_payload)
            if plan.plan_version != g07.plan_version:
                raise StageApplicationError("STAGE_PLAN_STALE", "The locked stage plan is stale.", status_code=409)
            definition = CommandRegistry().find(self.APPROVED_COMMAND_ID)
            approved_command = " ".join((definition.executable, *definition.arguments))
            if tuple(plan.approved_commands) != (approved_command,):
                raise StageApplicationError("UNSAFE_COMMAND", "The locked plan does not authorize the registered bootstrap command.", status_code=409)

            profile = session.scalar(select(ExecutionProfileModel).where(
                ExecutionProfileModel.run_id == run_id
            ).order_by(ExecutionProfileModel.updated_at.desc()))
            if profile is None or profile.status not in {"resolved", "selected", "completed"} or not profile.selected_profile_id:
                raise StageApplicationError("EXECUTION_PROFILE_MISMATCH", "A selected execution profile is required.", status_code=409)
            profile_data = next((p for p in profile.profiles if p.get("profile_id") == profile.selected_profile_id), None)
            if profile_data is None or (profile.selected_checksum and profile_data.get("checksum") != profile.selected_checksum):
                raise StageApplicationError("EXECUTION_PROFILE_MISMATCH", "The selected execution profile is stale.", status_code=409)
            if plan.toolchain_profile not in {"npm-ci", profile.selected_profile_id, profile_data.get("package_manager", "npm")}:
                raise StageApplicationError("EXECUTION_PROFILE_MISMATCH", "The runtime profile does not match the locked plan.", status_code=409)

            pre_fingerprint = self._dir_fingerprint(sandbox)
            if pre_fingerprint != workspace.workspace_fingerprint:
                raise StageApplicationError("WORKSPACE_FINGERPRINT_MISMATCH", "The stage sandbox changed after G07 approval.", status_code=409)
            if (sandbox / "node_modules").exists():
                raise StageApplicationError("PREEXISTING_DEPENDENCY_STATE", "Existing node_modules cannot be reused silently.", status_code=409)
            if not (sandbox / "package-lock.json").is_file():
                raise StageApplicationError("LOCKFILE_MISSING", "npm ci requires package-lock.json.", status_code=409)
            if not (sandbox / "package.json").is_file():
                raise StageApplicationError("LOCKFILE_MISMATCH", "package.json is missing for the approved npm lockfile.", status_code=409)
            lockfile_text = (sandbox / "package-lock.json").read_text(encoding="utf-8", errors="replace")
            try:
                lockfile_data = json.loads(lockfile_text)
            except json.JSONDecodeError:
                raise StageApplicationError("LOCKFILE_MISMATCH", "package-lock.json is not valid JSON.", status_code=409)
            lockfile_version = lockfile_data.get("lockfileVersion")
            if lockfile_version is None or not isinstance(lockfile_version, int) or lockfile_version < 2:
                raise StageApplicationError("LOCKFILE_MISMATCH", f"Unsupported lockfile version {lockfile_version}; npm ci requires lockfileVersion >= 2.", status_code=409)
            pkg_text = (sandbox / "package.json").read_text(encoding="utf-8", errors="replace")
            try:
                pkg_data = json.loads(pkg_text)
            except json.JSONDecodeError:
                raise StageApplicationError("LOCKFILE_MISMATCH", "package.json is not valid JSON.", status_code=409)
            pkg_name = pkg_data.get("name")
            lock_name = lockfile_data.get("name")
            if pkg_name and lock_name and pkg_name != lock_name:
                raise StageApplicationError("LOCKFILE_MISMATCH", f"package.json name '{pkg_name}' does not match package-lock.json name '{lock_name}'.", status_code=409)

            lifecycle_status = (g07.package or {}).get("lifecycle_script_status")
            if lifecycle_status is None:
                raise StageApplicationError("LIFECYCLE_SCRIPT_AUDIT_MISSING", "Lifecycle-script audit status is missing; G07 package must include lifecycle_script_status.", status_code=409)
            lifecycle_ref = (g07.package or {}).get("lifecycle_script_audit_ref")
            if lifecycle_ref is None:
                raise StageApplicationError("LIFECYCLE_SCRIPT_AUDIT_MISSING", "Lifecycle-script audit reference is required but missing.", status_code=409)
            if lifecycle_status not in _APPROVED_LIFECYCLE_STATUSES:
                if lifecycle_status in {"blocked", "denied", "approval_required"}:
                    raise StageApplicationError("LIFECYCLE_SCRIPT_BLOCKED", "Lifecycle-script governance blocks bootstrap installation.", status_code=409)
                raise StageApplicationError("LIFECYCLE_SCRIPT_AUTHORIZATION_MISSING", f"Lifecycle-script status '{lifecycle_status}' does not authorize bootstrap installation.", status_code=409)

            started = self._transition(session, run, request, WorkflowEventType.STAGE_BOOTSTRAP_INSTALL_STARTED,
                                       "Stage bootstrap install started", {"stage_id": stage_id, "command": "npm ci"})
            node_ver = (profile_data or {}).get("node_version")
            npm_ver = (profile_data or {}).get("npm_version")
            execution = CommandExecutionModel(
                id=f"cmd-{uuid4().hex[:12]}", run_id=run_id, stage_id=stage_id,
                idempotency_key=request.idempotency_key, requested_by=request.actor, requester=request.actor,
                executable=definition.executable, arguments=list(definition.arguments), working_directory_alias=self.WORKING_DIRECTORY_ALIAS,
                runtime_profile_id=profile.selected_profile_id, runtime_checksum=profile.selected_checksum,
                status=CommandStatus.PENDING.value, requested_at=now, command_id=self.APPROVED_COMMAND_ID,
                shell=False, timeout_seconds=self.TIMEOUT_SECONDS, network_profile=self.NETWORK_PROFILE,
                cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE.value,
                start_fingerprint={"workspace_fingerprint": pre_fingerprint, "lifecycle_script_audit_ref": lifecycle_ref,
                                   "node_version": node_ver, "npm_version": npm_ver},
                artifact_ids=[], blockers=[], state_version=started.next_state_version,
                event_sequence=started.event_sequence,
            )
            session.add(execution)
            session.add(StageStepModel(
                id=f"step-{uuid4().hex[:12]}", run_id=run_id, stage_id=stage_id, name=self.STEP_NAME,
                status="STARTING", component_type="StagePipelineService", attempt_id=execution.id,
                idempotency_key=request.idempotency_key, started_at=now,
            ))
            session.flush()
            return execution.id, sandbox, profile.selected_profile_id, pre_fingerprint, workspace.id, g07.id

    def _execute(self, run_id, stage_id, execution_id, sandbox, profile_id, pre_fingerprint, workspace_id, g07_id, request):
        now = self._now()
        with self._scope() as session:
            run = self._run(session, run_id)
            execution = session.get(CommandExecutionModel, execution_id)
            step = self._step(session, run_id, stage_id, execution_id)
            execution.status = CommandStatus.RUNNING.value
            execution.started_at = now
            step.status = "RUNNING"
            started = self._transition(session, run, request, WorkflowEventType.COMMAND_STARTED, "npm ci started",
                                       {"stage_id": stage_id, "command_id": execution_id})
            execution.state_version, execution.event_sequence = started.next_state_version, started.event_sequence

        run = self._run_by_id(run_id)
        worker = self._worker(run, sandbox, profile_id)
        definition = CommandRegistry().find(self.APPROVED_COMMAND_ID)
        command_request = CommandRequestDto(
            command_id=definition.command_id, run_id=run_id, stage_id=stage_id,
            requested_by=request.actor, requester=request.actor,
            executable=definition.executable, arguments=list(definition.arguments), shell=False,
            working_directory_alias=self.WORKING_DIRECTORY_ALIAS, runtime_profile_id=profile_id,
            timeout_seconds=self.TIMEOUT_SECONDS, network_profile=self.NETWORK_PROFILE,
            cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
            idempotency_key=request.idempotency_key, requested_at=now,
        )
        try:
            result = worker.run(command_request)
        except Exception as exc:
            return self._finalize_internal_failure(run_id, stage_id, execution_id, request, "COMMAND_EXECUTION_FAILURE", exc)
        post_fingerprint = self._dir_fingerprint(sandbox)
        failure_code = self._classify(result)
        result_success = result.result.status is CommandStatus.SUCCEEDED
        interrupted = result.cancelled or result.timed_out
        if result_success:
            final_status = "COMPLETED"
        elif result.cancelled and not result.timed_out:
            final_status = "CANCELLED"
        elif result.timed_out:
            final_status = "INTERRUPTED"
        else:
            final_status = "FAILED"
        artifacts = [result.command_log_artifact]
        if result.stdout_artifact: artifacts.append(result.stdout_artifact)
        if result.stderr_artifact: artifacts.append(result.stderr_artifact)

        try:
            with self._scope() as session:
                run = self._run(session, run_id)
                execution = session.get(CommandExecutionModel, execution_id)
                step = self._step(session, run_id, stage_id, execution_id)
                workspace = session.get(StageWorkspaceModel, workspace_id)
                g07 = session.get(G07ApprovalModel, g07_id)
                if execution is None or step is None or execution.status != CommandStatus.RUNNING.value:
                    return self._finalize_internal_failure(run_id, stage_id, execution_id, request, "STALE_BOOTSTRAP_EXECUTION", StageApplicationError("STALE_BOOTSTRAP_EXECUTION", "Execution ownership changed during command.", status_code=409))
                if workspace is None or Path(workspace.sandbox_path).resolve() != sandbox.resolve():
                    return self._finalize_internal_failure(run_id, stage_id, execution_id, request, "STAGE_SANDBOX_STALE", StageApplicationError("STAGE_SANDBOX_STALE", "Sandbox changed during command.", status_code=409))
                if g07 is None or g07.status not in {"approved", "approved_with_comment"} or g07.package.get("workspace_fingerprint") != pre_fingerprint:
                    return self._finalize_internal_failure(run_id, stage_id, execution_id, request, "STALE_G07_DECISION", StageApplicationError("STALE_G07_DECISION", "G07 changed during command.", status_code=409))
                artifact_metadatas = []
                artifact_ids = []
                try:
                    for artifact in artifacts:
                        am = ArtifactMetadataModel(
                            id=f"metadata-{artifact.ref.artifact_id}", run_id=run_id, stage_id=stage_id,
                            artifact_type=artifact.ref.artifact_type.value, relative_path=artifact.ref.relative_path,
                            checksum=artifact.ref.checksum, created_at=artifact.ref.created_at,
                        )
                        session.add(am)
                        artifact_metadatas.append(am)
                        artifact_ids.append(artifact.ref.artifact_id)
                    summary = self._write_summary(run, stage_id, execution_id, pre_fingerprint, post_fingerprint,
                                                  result.result.status.value, result.result.exit_code, failure_code, interrupted)
                    am = ArtifactMetadataModel(
                        id=f"metadata-{summary.ref.artifact_id}", run_id=run_id, stage_id=stage_id,
                        artifact_type=summary.ref.artifact_type.value, relative_path=summary.ref.relative_path,
                        checksum=summary.ref.checksum, created_at=summary.ref.created_at,
                    )
                    session.add(am)
                    artifact_metadatas.append(am)
                    artifact_ids.append(summary.ref.artifact_id)
                except Exception as exc:
                    return self._finalize_internal_failure(run_id, stage_id, execution_id, request, "ARTIFACT_PERSISTENCE_FAILURE", exc)
                execution.status = result.result.status.value
                execution.exit_code = result.result.exit_code
                execution.finished_at = result.result.finished_at
                execution.duration_ms = result.result.duration_ms
                execution.timed_out = result.timed_out
                execution.cancelled = result.cancelled
                execution.reconstruction_required = interrupted and not result_success
                execution.stdout_artifact_id = result.stdout_artifact.ref.artifact_id if result.stdout_artifact else None
                execution.stderr_artifact_id = result.stderr_artifact.ref.artifact_id if result.stderr_artifact else None
                execution.command_log_artifact_id = result.command_log_artifact.ref.artifact_id
                execution.artifact_ids = artifact_ids
                execution.end_fingerprint = {"workspace_fingerprint": post_fingerprint}
                execution.blockers = [failure_code] if failure_code else []
                execution.environment_blocker = failure_code
                step.status = final_status
                step.completed_at = result.result.finished_at
                if final_status == "COMPLETED":
                    event = WorkflowEventType.STAGE_BOOTSTRAP_INSTALL_COMPLETED
                else:
                    event = WorkflowEventType.STAGE_BOOTSTRAP_INSTALL_FAILED
                try:
                    finalized = self._transition(session, run, request, event, f"Stage bootstrap install {final_status.lower()}", {
                        "stage_id": stage_id, "command_id": execution_id, "status": final_status,
                        "artifact_ids": artifact_ids, "failure_code": failure_code, "reconstruction_required": interrupted,
                    })
                except Exception as exc:
                    return self._finalize_internal_failure(run_id, stage_id, execution_id, request, "EVENT_PERSISTENCE_FAILURE", exc)
                execution.state_version, execution.event_sequence = finalized.next_state_version, finalized.event_sequence
                return self._response(session, execution)
        except StageApplicationError:
            raise
        except Exception as exc:
            return self._finalize_internal_failure(run_id, stage_id, execution_id, request, "INTERNAL_EXECUTION_FAILURE", exc)

    def _finalize_internal_failure(self, run_id, stage_id, execution_id, request, code, exc):
        with self._scope() as session:
            run = self._run(session, run_id)
            execution = session.get(CommandExecutionModel, execution_id)
            step = self._step(session, run_id, stage_id, execution_id)
            if execution is None or step is None:
                raise StageApplicationError(code, "Bootstrap execution failed before durable evidence could be finalized.", status_code=500) from exc
            finished = self._now()
            execution.status = CommandStatus.FAILED.value
            execution.finished_at = finished
            execution.environment_blocker = code
            execution.blockers = [code]
            execution.reconstruction_required = True
            step.status = "RECOVERY_REQUIRED"
            step.completed_at = finished
            finalized = self._transition(session, run, request, WorkflowEventType.STAGE_BOOTSTRAP_INSTALL_FAILED,
                "Stage bootstrap install failed before command evidence finalization",
                {"stage_id": stage_id, "command_id": execution_id, "status": "RECOVERY_REQUIRED",
                 "failure_code": code, "reconstruction_required": True})
            execution.state_version = finalized.next_state_version
            execution.event_sequence = finalized.event_sequence
            return self._response(session, execution)

    def get_bootstrap_status(self, run_id: str, stage_id: str) -> StageBootstrapStatusResponse | None:
        with self._scope() as session:
            execution = session.scalar(select(CommandExecutionModel).where(
                CommandExecutionModel.run_id == run_id, CommandExecutionModel.stage_id == stage_id,
                CommandExecutionModel.command_id == self.APPROVED_COMMAND_ID,
            ).order_by(CommandExecutionModel.requested_at.desc()))
            return self._status_response(session, execution) if execution else None

    def _worker(self, run, sandbox: Path, profile_id: str):
        if self._worker_factory is not None:
            return self._worker_factory(run, sandbox, profile_id)
        root = Path(run.artifact_root).resolve()
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        policy = CommandPolicy(
            sandbox_root=sandbox, working_directory_aliases={self.WORKING_DIRECTORY_ALIAS: sandbox},
            runtime_profiles=frozenset({profile_id}), network_profiles=frozenset({self.NETWORK_PROFILE}),
        )
        return ExecutionWorker(policy, CommandLogWriter(store, max_output_bytes=None))

    def _write_summary(self, run, stage_id, execution_id, pre, post, status, exit_code, failure_code, interrupted):
        root = Path(run.artifact_root).resolve()
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        payload = {"run_id": run.id, "stage_id": stage_id, "execution_id": execution_id, "command": "npm ci",
                   "status": status, "exit_code": exit_code, "failure_code": failure_code,
                   "pre_workspace_fingerprint": pre, "post_workspace_fingerprint": post,
                   "recovery": "reconstruct_stage_sandbox" if interrupted else None,
                   "retry_eligible": not interrupted and status != CommandStatus.SUCCEEDED.value}
        return store.write_text_artifact(run.id, f"04_workflow_state/stages/{stage_id}/bootstrap-install-result.json",
                                         json.dumps(payload, indent=2, sort_keys=True), ArtifactType.JSON,
                                         stage_id=stage_id, created_by="stage-bootstrap-service", created_at=self._now())

    @staticmethod
    def _classify(result) -> str | None:
        if result.timed_out: return "COMMAND_TIMEOUT"
        if result.cancelled: return "INTERRUPTED_MUTATION"
        if result.result.status is CommandStatus.SUCCEEDED: return None
        text = ""
        if result.stderr_artifact:
            text = result.stderr_artifact.content
        lowered = text.lower()
        if "e401" in lowered or "unauthorized" in lowered or "authentication" in lowered: return "REGISTRY_AUTHENTICATION_FAILURE"
        if "enotfound" in lowered or "network" in lowered or "econn" in lowered: return "NETWORK_FAILURE"
        if "eresolve" in lowered or "could not resolve" in lowered: return "PACKAGE_RESOLUTION_FAILURE"
        if "registry" in lowered: return "REGISTRY_FAILURE"
        if result.result.status is CommandStatus.REJECTED: return "UNSAFE_COMMAND"
        return "UNKNOWN_COMMAND_FAILURE"

    @staticmethod
    def _authorized_sandbox(run, workspace) -> Path:
        sandbox = Path(workspace.sandbox_path).resolve()
        aliases = run.workspace_aliases or {}
        registered_raw = aliases.get("STAGE_SANDBOX")
        if registered_raw is None:
            raise StageApplicationError("STAGE_SANDBOX_MISSING", "The STAGE_SANDBOX alias is not registered in run workspace_aliases.", status_code=409)
        registered = Path(registered_raw).resolve()
        if sandbox != registered:
            raise StageApplicationError("STAGE_SANDBOX_STALE", "The workspace path does not match the registered stage sandbox alias.", status_code=409)
        run_root_raw = run.run_root
        if run_root_raw:
            run_root = Path(run_root_raw).resolve()
            if run_root.is_dir():
                try:
                    sandbox.relative_to(run_root)
                except ValueError:
                    raise StageApplicationError("SOURCE_SAFETY_VIOLATION", "The stage sandbox is outside the managed run root.", status_code=409)
        source_candidates = [aliases.get("SOURCE_SNAPSHOT"), aliases.get("IMMUTABLE_SOURCE")]
        for alias_name in ("SOURCE_SNAPSHOT", "IMMUTABLE_SOURCE"):
            alias_val = aliases.get(alias_name)
            if alias_val and Path(alias_val).resolve() == sandbox:
                raise StageApplicationError("SOURCE_SAFETY_VIOLATION", f"Bootstrap execution cannot target immutable source ({alias_name}).", status_code=409)
        if not sandbox.is_dir():
            raise StageApplicationError("STAGE_SANDBOX_MISSING", "The stage sandbox directory is missing.", status_code=409)
        try:
            sandbox.resolve().relative_to(sandbox.resolve())
        except (ValueError, RuntimeError):
            pass
        return sandbox

    @staticmethod
    def _dir_fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        for item in sorted((p for p in path.rglob("*") if p.is_file() and "node_modules" not in p.parts), key=lambda p: p.as_posix()):
            relative = item.relative_to(path).as_posix().encode()
            digest.update(relative); digest.update(b"\0")
            with item.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
        return f"sha256:{digest.hexdigest()}"

    def _transition(self, session, run, request, event, reason, payload):
        return StateTransitionService(session).apply_transition(TransitionRequest(
            run_id=run.id, expected_state_version=run.state_version,
            idempotency_key=f"{request.idempotency_key}:{event.value}", event_type=event,
            actor=request.actor, reason=reason, occurred_at=self._now(), payload=payload,
        ))

    @staticmethod
    def _run(session, run_id):
        run = session.get(MigrationRunModel, run_id)
        if run is None: raise StageApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
        return run

    def _run_by_id(self, run_id):
        with self._scope() as session: return self._run(session, run_id)

    @staticmethod
    def _step(session, run_id, stage_id, execution_id):
        return session.scalar(select(StageStepModel).where(
            StageStepModel.run_id == run_id, StageStepModel.stage_id == stage_id,
            StageStepModel.name == StageBootstrapApplicationService.STEP_NAME,
            StageStepModel.attempt_id == execution_id,
        ))

    def _response(self, session, execution, *, idempotent_replay=False):
        status = self._status_response(session, execution)
        return StageBootstrapInstallResponse(**status.model_dump(), idempotent_replay=idempotent_replay)

    def _status_response(self, session, execution):
        step = self._step(session, execution.run_id, execution.stage_id, execution.id)
        status = step.status if step else execution.status
        start = execution.start_fingerprint or {}; end = execution.end_fingerprint or {}
        g07 = session.scalar(select(G07ApprovalModel).where(
            G07ApprovalModel.run_id == execution.run_id, G07ApprovalModel.stage_id == execution.stage_id
        ).order_by(G07ApprovalModel.created_at.desc(), G07ApprovalModel.id.desc()))
        g07_status = g07.status if g07 else None
        g07_stale = False
        if g07 and g07.status in {"approved", "approved_with_comment"}:
            ws_fp = (execution.start_fingerprint or {}).get("workspace_fingerprint")
            if ws_fp and g07.package.get("workspace_fingerprint") != ws_fp:
                g07_stale = True
        elif g07 is None:
            g07_status = "missing"
        return StageBootstrapStatusResponse(
            run_id=execution.run_id, stage_id=execution.stage_id, step_id=step.id if step else execution.id,
            name=self.STEP_NAME, status=status, command="npm ci", exit_code=execution.exit_code,
            started_at=execution.started_at, completed_at=execution.finished_at,
            state_version=execution.state_version or 1, event_sequence=execution.event_sequence or 1,
            artifact_ids=execution.artifact_ids or [], runtime_profile=execution.runtime_profile_id,
            stage_sandbox="STAGE_SANDBOX", g07_status=g07_status,
            lifecycle_script_audit_ref=start.get("lifecycle_script_audit_ref"),
            pre_fingerprint=start.get("workspace_fingerprint"), post_fingerprint=end.get("workspace_fingerprint"),
            failure_classification=execution.environment_blocker, blocker_code=execution.environment_blocker,
            retry_eligible=bool(not execution.reconstruction_required and execution.environment_blocker and not g07_stale),
            recovery_required=bool(execution.reconstruction_required or g07_stale),
            reconstruction_guidance="Reconstruct the authoritative stage sandbox before retrying." if execution.reconstruction_required or g07_stale else None,
            correlation_id=execution.id,
        )
