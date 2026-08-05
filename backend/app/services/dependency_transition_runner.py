"""Post-G10 governed dependency-transition (detach/update/reattach) execution.

Phase progress is derived entirely from durable execution rows keyed by
idempotency keys, so restarts are safe: the graph's "dependency_transition"
node re-dispatches this runner on every wake and each phase resumes from the
terminal evidence already persisted. The workspace restore to the
pre_angular_update checkpoint is performed by the graph handler
(``_restore_angular_update_checkpoint``), never by this runner.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from app.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
)
from app.domain.command import (
    NPM_DEPENDENCY_INSTALL_RENDERER,
    NPM_DEPENDENCY_UNINSTALL_RENDERER,
)
from app.domain.contracts import ArtifactType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    MigrationPlanModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
)
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
)
from app.services.dependency_closure_service import (
    compatible_reinstall_version,
    is_exact_version,
    verify_dependency_closure,
    verify_dependency_transition_state,
)
from app.services.repair_application_service import RepairProposal
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE


class DependencyTransitionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _file_checksum(path: Path) -> str:
    return (
        "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_file() and not path.is_symlink()
        else "missing"
    )


def _version_major(value: object) -> int | None:
    match = re.match(r"\s*[~^]?\s*(\d+)", str(value or ""))
    return int(match.group(1)) if match else None

def _dependency_evidence(workspace: Path, packages: tuple[str, ...]) -> dict[str, object]:
    workspace = Path(workspace)
    manifest_path = workspace / "package.json"
    manifest = _read_json_document(manifest_path)
    lock = _read_json_document(workspace / "package-lock.json")
    lock_packages = lock.get("packages") if isinstance(lock, dict) else None
    lockfiles = {
        name: _file_checksum(workspace / name)
        for name in ("package-lock.json", "npm-shrinkwrap.json")
        if (workspace / name).is_file()
    }
    installed: dict[str, object] = {}
    manifest_entries: dict[str, object] = {}
    lockfile_entries: dict[str, object] = {}
    for package in sorted(set(packages)):
        manifest_entries[package] = next(
            (
                {"section": section, "range": manifest[section][package]}
                for section in ("dependencies", "devDependencies")
                if isinstance(manifest.get(section), dict) and package in manifest[section]
            ),
            None,
        )
        root = lock_packages.get("") if isinstance(lock_packages, dict) else None
        root_entry = next(
            (
                {"section": section, "range": root[section][package]}
                for section in ("dependencies", "devDependencies")
                if isinstance(root, dict)
                and isinstance(root.get(section), dict)
                and package in root[section]
            ),
            None,
        )
        package_entry = (
            lock_packages.get(f"node_modules/{package}")
            if isinstance(lock_packages, dict)
            else None
        )
        lockfile_entries[package] = {
            "root": root_entry,
            "version": package_entry.get("version") if isinstance(package_entry, dict) else None,
        }
        installed_path = workspace / "node_modules" / package / "package.json"
        version = None
        try:
            document = json.loads(installed_path.read_text(encoding="utf-8"))
            version = document.get("version") if isinstance(document, dict) else None
        except (OSError, ValueError):
            pass
        installed[package] = {
            "path": f"node_modules/{package}/package.json",
            "sha256": _file_checksum(installed_path),
            "version": version,
        }
    return {
        "package_json_sha256": _file_checksum(manifest_path),
        "package_json_content": manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else None,
        "manifest_entries": manifest_entries,
        "lockfiles": lockfiles,
        "lockfile_entries": lockfile_entries,
        "installed_packages": installed,
    }


def _read_json_document(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _package_json_change(before: object, after: dict[str, object]) -> dict[str, object]:
    previous = before if isinstance(before, dict) else {}
    old_content = previous.get("package_json_content")
    new_content = after.get("package_json_content")
    diff = ""
    if isinstance(old_content, str) and isinstance(new_content, str):
        diff = "".join(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile="a/package.json",
                tofile="b/package.json",
            )
        )
    return {
        "before_checksum": previous.get("package_json_sha256"),
        "after_checksum": after.get("package_json_sha256"),
        "unified_diff": diff or None,
    }

class DependencyTransitionRunner:
    def __init__(self, *, stage_service=None, command_executor=None, now_provider=None) -> None:
        self._stage = stage_service or TransformerStageService()
        self._command_executor = (
            command_executor
            or getattr(self._stage, "_command_executor", None)
            or CommandExecutorService()
        )
        self._now = now_provider or (lambda: datetime.now(UTC))

    def advance(self, session, continuation) -> str:
        context = self._context(session, continuation)
        if context["attempt"].status in {"applied", "transition_complete", "applied_verified"}:
            self._resume(continuation, "target_inspection")
            return "passed"
        if context["attempt"].status == "approved_pending_execution":
            context["attempt"].status = "executing"
            context["attempt"].updated_at = self._now()
            self._resume(continuation, "dependency_transition")
            return "queued"
        if context["attempt"].status != "executing":
            context["attempt"].status = "executing"
            context["attempt"].updated_at = self._now()
        phase = self._current_phase(session, continuation, context)
        if phase == "uninstall":
            outcome = self._phase_uninstall(session, continuation, context)
        elif phase == "angular_update":
            outcome = self._phase_update(session, continuation, context)
        elif phase == "reinstall":
            outcome = self._phase_install(session, continuation, context)
        elif phase == "npm_ci":
            outcome = self._phase_ci(session, continuation, context)
        elif phase == "dependency_closure":
            outcome = self._phase_closure(session, continuation, context)
        else:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_PHASE_INVALID",
                f"Unknown dependency-transition phase: {phase}",
            )
        if outcome != "continue":
            return outcome
        self._resume(continuation, "dependency_transition")
        return "queued"

    def _current_phase(self, session, continuation, context) -> str:
        uninstall = self._execution(
            session, context, f"{context['attempt'].id}:transition:uninstall"
        )
        uninstall_verified = uninstall is not None and session.scalar(
            select(ArtifactMetadataModel.id).where(
                ArtifactMetadataModel.owner_reference
                == f"{uninstall.id}:dependency-transition-uninstall"
            )
        )
        if uninstall is None or uninstall.status != "succeeded" or not uninstall_verified:
            return "uninstall"
        angular_step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        if angular_step is None or angular_step.status != "PASSED":
            return "angular_update"
        install = self._execution(
            session, context, f"{context['attempt'].id}:transition:install"
        )
        install_verified = install is not None and session.scalar(
            select(ArtifactMetadataModel.id).where(
                ArtifactMetadataModel.owner_reference
                == f"{install.id}:dependency-transition-install"
            )
        )
        if install is None or install.status != "succeeded" or not install_verified:
            return "reinstall"
        ci_step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "final_install-0",
            )
        )
        return "npm_ci" if ci_step is None or ci_step.status != "PASSED" else "dependency_closure"

    def _context(self, session, continuation) -> dict[str, object]:
        run = session.get(MigrationRunModel, continuation.run_id)
        attempt = session.scalar(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
        )
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        if (
            run is None
            or attempt is None
            or binding is None
            or stage_plan is None
            or plan is None
            or not run.artifact_root
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_AUTHORITY_MISSING",
                "Dependency-transition authority is incomplete",
            )
        if attempt.status not in {
            "approved_pending_execution",
            "executing",
            "uninstall",
            "angular_update",
            "reinstall",
            "npm_ci",
            "dependency_closure",
            "applied",
            "applied_verified",
            "transition_complete",
        }:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_NOT_APPROVED",
                "No approved dependency_transition authorizes this execution",
            )
        try:
            workspace = Path(binding.workspace_path).resolve(strict=True)
            workspace.relative_to(Path(run.run_root).resolve(strict=True))
        except (OSError, ValueError) as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_WORKSPACE_INVALID",
                "The bound stage workspace is unavailable or outside the run root",
            ) from error
        intent = self._intent(session, continuation, run, attempt, stage_plan, plan, workspace)
        return {
            "run": run,
            "attempt": attempt,
            "binding": binding,
            "workspace": workspace,
            "stage_plan": stage_plan,
            "plan": plan,
            "intent": intent,
        }

    def _intent(
        self,
        session,
        continuation,
        run,
        attempt,
        stage_plan,
        plan,
        workspace,
    ) -> dict[str, object]:
        if not attempt.proposal_artifact_id or not attempt.proposal_checksum:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_NOT_APPROVED",
                "Applied repair attempt has no bound proposal artifact",
            )
        metadata = session.get(
            ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id)
        )
        if metadata is None or metadata.checksum != attempt.proposal_checksum:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_NOT_APPROVED",
                "Applied repair proposal artifact binding is stale",
            )
        store = LocalFilesystemArtifactStore(
            Path(str(run.artifact_root)).parent,
            fixed_run_root=Path(str(run.artifact_root)),
        )
        try:
            stored = store.read_artifact(continuation.run_id, metadata.relative_path)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError) as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_NOT_APPROVED",
                "Applied repair proposal artifact cannot be read",
            ) from error
        if (
            stored.ref.artifact_id != attempt.proposal_artifact_id
            or stored.ref.checksum != attempt.proposal_checksum
            or stored.envelope is None
            or stored.envelope.run_id != continuation.run_id
            or stored.envelope.stage_id != continuation.current_stage_id
            or stored.envelope.attempt_id != attempt.id
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_NOT_APPROVED",
                "Applied repair proposal artifact identity changed",
            )
        try:
            proposal = RepairProposal.model_validate(json.loads(stored.content))
        except (OSError, ValueError) as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_NOT_APPROVED",
                "Applied repair proposal artifact is invalid",
            ) from error
        transitions = [
            item for item in proposal.operations if item.operation == "dependency_transition"
        ]
        if len(proposal.operations) != 1 or len(transitions) != 1:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INTENT_INVALID",
                "The applied proposal must contain exactly one dependency_transition operation",
            )
        operation = transitions[0]
        if (
            operation.schema_version != "transformer-repair-v2"
            or operation.repair_kind != "dependency_transition"
            or operation.failure_type != "peer_dependency_conflict"
            or operation.strategy != "detach_update_reattach"
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INTENT_INVALID",
                "dependency_transition intent fields are invalid",
            )
        blocking = operation.blocking_dependency
        target_state = operation.target_state
        blocking_package = blocking.package if blocking is not None else None
        installed_version = blocking.installed_version if blocking is not None else None
        peer_ranges = (
            {
                item.package: item.version_range
                for item in blocking.required_peer_ranges
            }
            if blocking is not None
            else None
        )
        target_version = target_state.target_version if target_state is not None else None
        angular_major = target_state.angular_major if target_state is not None else None
        try:
            approved_target_version = compatible_reinstall_version(
                str(blocking_package or ""), int(angular_major) if isinstance(angular_major, int) else -1
            )
        except ValueError as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INTENT_INVALID", str(error)
            ) from error
        if (
            target_state is None
            or target_state.package != blocking_package
            or not isinstance(blocking_package, str)
            or not blocking_package
            or not is_exact_version(installed_version)
            or not isinstance(peer_ranges, dict)
            or not isinstance(target_version, str)
            or not is_exact_version(target_version)
            or not isinstance(angular_major, int)
            or target_version != approved_target_version
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INTENT_INVALID",
                "dependency_transition blocking_dependency or target_state is incomplete",
            )
        stage_data = stage_plan.stage_plan or {}
        references = (stage_data.get("commands") or {}).get("angular_update") or []
        planned = references[0] if len(references) == 1 else None
        bindings = (planned or {}).get("parameter_bindings") or {}
        target_exact = bindings.get("target_exact") or stage_data.get("target_exact")
        target_cli_exact = (
            bindings.get("target_cli_exact")
            or stage_data.get("target_cli_exact")
            or target_exact
        )
        target_major = _version_major(target_exact)
        if (
            planned is None
            or planned.get("command_id") != "angular-update-exact"
            or not is_exact_version(target_exact)
            or not is_exact_version(target_cli_exact)
            or target_major is None
            or target_major != angular_major
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INTENT_INVALID",
                "The approved stage plan lacks the exact angular-update authority for the transition",
            )
        return {
            "blocking_package": blocking_package,
            "installed_version": installed_version,
            "peer_ranges": dict(peer_ranges),
            "target_version": target_version,
            "angular_major": angular_major,
            "target_exact": str(target_exact or ""),
            "target_cli_exact": str(target_cli_exact or ""),
            "execution_profile_id": str(stage_data.get("execution_profile_id") or ""),
            "plan_id": plan.id,
            "plan_version": plan.version,
        }

    def _execution(self, session, context, key: str):
        return session.scalar(
            select(CommandExecutionModel).where(
                CommandExecutionModel.run_id == context["run"].id,
                CommandExecutionModel.idempotency_key == key,
            )
        )
    def _completed_uninstall(self, session, context, arguments):
        executions = session.scalars(
            select(CommandExecutionModel)
            .where(
                CommandExecutionModel.run_id == context["run"].id,
                CommandExecutionModel.command_id == "npm-dependency-uninstall",
                CommandExecutionModel.status == "succeeded",
                CommandExecutionModel.exit_code == 0,
            )
            .order_by(CommandExecutionModel.finished_at.desc())
        ).all()
        return next(
            (execution for execution in executions if list(execution.arguments or []) == list(arguments)),
            None,
        )

    def _phase_uninstall(self, session, continuation, context) -> str:
        key = f"{context['attempt'].id}:transition:uninstall"
        execution = self._execution(session, context, key)
        if execution is None:
            arguments = NPM_DEPENDENCY_UNINSTALL_RENDERER.render_arguments(
                {"package": context["intent"]["blocking_package"]}
            )
            execution = self._completed_uninstall(session, context, arguments)
            if execution is not None:
                self._verify_uninstall(session, continuation, context, execution)
                return "continue"
            try:
                verify_dependency_transition_state(
                    context["workspace"],
                    package=context["intent"]["blocking_package"],
                    installed_version=context["intent"]["installed_version"],
                    peer_ranges=context["intent"]["peer_ranges"],
                )
            except ValueError as error:
                raise DependencyTransitionError(
                    "DEPENDENCY_TRANSITION_EVIDENCE_INVALID", str(error)
                ) from error
            return self._queue_transition_command(session, continuation, context, "uninstall", key)
        if execution.status in {"pending", "queued", "running"}:
            self._stage._wait_for_command(session, continuation, execution.id)
            return "waiting"
        if execution.status != "succeeded" or execution.exit_code != 0:
            raise DependencyTransitionError(
                execution.failure_code or "DEPENDENCY_TRANSITION_COMMAND_FAILED",
                execution.failure_message or "npm uninstall did not succeed",
            )
        self._verify_uninstall(session, continuation, context, execution)
        return "continue"

    def _queue_transition_command(self, session, continuation, context, phase, key) -> str:
        run = context["run"]
        attempt = context["attempt"]
        binding = context["binding"]
        workspace = context["workspace"]
        intent = context["intent"]
        if phase == "uninstall":
            renderer = NPM_DEPENDENCY_UNINSTALL_RENDERER
            bindings = {"package": intent["blocking_package"]}
        else:
            renderer = NPM_DEPENDENCY_INSTALL_RENDERER
            bindings = {
                "package": intent["blocking_package"],
                "target_version": intent["target_version"],
            }
        try:
            arguments = list(renderer.render_arguments(bindings))
            authorization_id = self._command_executor.authorize_dependency_transition_command(
                session,
                attempt_id=attempt.id,
                command_id=renderer.command_id,
                executable=renderer.executable,
                arguments=arguments,
                working_directory_alias=binding.alias,
                working_directory=binding.workspace_path,
                plan_id=intent["plan_id"],
                plan_version=intent["plan_version"],
                execution_profile_id=intent["execution_profile_id"],
                network_profile=renderer.network_profile,
                timeout_seconds=renderer.timeout_seconds,
                idempotency_key=key,
            )
        except CommandExecutorError as error:
            raise DependencyTransitionError(error.code, error.message) from error
        except (TypeError, ValueError) as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INTENT_INVALID",
                "Dependency-transition command arguments cannot be rendered",
            ) from error
        authorization = session.get(CommandAuthorizationAuditModel, authorization_id)
        if authorization is None:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_AUTHORIZATION_MISSING",
                "Dependency-transition authorization is missing",
            )
        try:
            result = self._command_executor.queue_authorized_command(
                session,
                run_id=run.id,
                authorization_decision_id=authorization_id,
                expected_state_version=run.state_version,
                idempotency_key=key,
                requested_by="transformer",
                correlation_id=authorization.correlation_id,
            )
        except CommandExecutorError as error:
            raise DependencyTransitionError(error.code, error.message) from error
        execution = session.get(CommandExecutionModel, result.execution_id)
        if execution is None:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_QUEUE_FAILED",
                "Queued transition command evidence is missing",
            )
        execution.timeout_seconds = renderer.timeout_seconds
        dependency = _dependency_evidence(workspace, (intent["blocking_package"],))
        execution.start_fingerprint = {
            "canonical_source": binding.workspace_fingerprint,
            "dependency": dependency,
            "package_json_sha256": _file_checksum(workspace / "package.json"),
            f"node_modules_{intent['blocking_package'].replace('/', '_')}_package_json_sha256": (
                _file_checksum(workspace / "node_modules" / intent["blocking_package"] / "package.json")
            ),
            "binding_fingerprint": binding.workspace_fingerprint,
        }
        self._stage._wait_for_command(session, continuation, execution.id)
        return "queued"

    def _verify_uninstall(self, session, continuation, context, execution) -> None:
        run = context["run"]
        attempt = context["attempt"]
        binding = context["binding"]
        workspace = context["workspace"]
        intent = context["intent"]
        package = intent["blocking_package"]
        package_doc = self._read_package_json(workspace)
        manifest_has = any(
            isinstance(package_doc.get(section), dict) and package in package_doc[section]
            for section in ("dependencies", "devDependencies")
        )
        installed_present = (workspace / "node_modules" / package / "package.json").is_file()
        if manifest_has or installed_present:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_UNINSTALL_VERIFICATION_FAILED",
                "npm uninstall left the blocking dependency in package.json or node_modules",
            )
        existing_checkpoint = session.scalar(
            select(StageCheckpointModel)
            .where(
                StageCheckpointModel.run_id == continuation.run_id,
                StageCheckpointModel.stage_id == continuation.current_stage_id,
                StageCheckpointModel.kind == "post_repair",
                StageCheckpointModel.created_from_execution_id == execution.id,
            )
            .order_by(StageCheckpointModel.sequence.desc())
            .limit(1)
        )
        if existing_checkpoint is None:
            snapshot = self._stage.snapshot_workspace(
                binding.workspace_path,
                (run.workspace_aliases or {})["STAGE_SANDBOX"],
                continuation.current_stage_id,
            )
            checkpoint_fingerprint = snapshot.fingerprint
        else:
            snapshot = None
            checkpoint_fingerprint = existing_checkpoint.workspace_fingerprint
        dependency = _dependency_evidence(workspace, (package,))
        execution.end_fingerprint = {
            "canonical_source": checkpoint_fingerprint,
            "dependency": dependency,
        }
        payload = {
            "schema_version": "dependency-transition-uninstall-verification.v1",
            "phase": "uninstall",
            "execution_id": execution.id,
            "correlation_id": execution.correlation_id,
            "package": package,
            "pre_command": execution.start_fingerprint or {},
            "post_command": {
                "package_json_sha256": dependency["package_json_sha256"],
                "package_json_contains_blocking_package": manifest_has,
                "node_modules_blocking_package_present": installed_present,
            },
            "dependency_evidence": dependency,
            "package_json_change": _package_json_change(
                (execution.start_fingerprint or {}).get("dependency"), dependency
            ),
            "lockfile_changes": {
                "before": ((execution.start_fingerprint or {}).get("dependency") or {}).get("lockfile_entries"),
                "after": dependency.get("lockfile_entries"),
            },
            "workspace_fingerprint": checkpoint_fingerprint,
            "binding_fingerprint": binding.workspace_fingerprint,
        }
        stored = self._write_or_recover_verification(
            session,
            run,
            continuation,
            f"{execution.id}.dependency-transition-uninstall",
            payload,
        )
        self._register_verification_metadata(
            session,
            continuation,
            stored,
            execution_id=execution.id,
            owner_reference=f"{execution.id}:dependency-transition-uninstall",
        )
        if snapshot is not None:
            self._stage._checkpoint(
                session,
                continuation,
                snapshot,
                "post_repair",
                stored.ref.artifact_id,
                stored.ref.checksum,
                execution.id,
            )
            self._update_binding_fingerprint(session, continuation, binding, snapshot.fingerprint)
    def _phase_update(self, session, continuation, context) -> str:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        if step is None:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_ANGULAR_EVIDENCE_MISSING",
                "The angular_update-0 step is missing",
            )
        if step.status == "PASSED":
            return "continue"
        execution = (
            session.get(CommandExecutionModel, step.execution_id)
            if step.execution_id
            else None
        )
        if execution is None:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_ANGULAR_EVIDENCE_MISSING",
                "The angular update execution evidence is missing",
            )
        if execution.status in {"pending", "queued", "running"}:
            self._stage._wait_for_command(session, continuation, execution.id)
            return "waiting"
        if execution.status == "succeeded":
            live = STAGE_FINGERPRINT_PROFILE.fingerprint(context["workspace"])
            dependency = _dependency_evidence(
                context["workspace"], ("@angular/core", "@angular/cli", "@angular-devkit/build-angular")
            )
            execution.end_fingerprint = {
                "canonical_source": live,
                "dependency": dependency,
            }
            step.status = "PASSED"
            step.completed_at = self._now()
            step.workspace_fingerprint = live
            step.updated_at = self._now()
            if live != context["binding"].workspace_fingerprint:
                self._update_binding_fingerprint(session, continuation, context["binding"], live)
            return "continue"
        # Terminal failure: queue the governed retry of the failed angular update
        # (the v2->v3 supersession path; the runner stays in control until the
        # retry is queued, then handle_prompt owns the outcome).
        try:
            self._stage.queue_angular_update_retry(
                session,
                continuation,
                failed_execution_id=execution.id,
                idempotency_key=f"{execution.id}:retry:post-repair:{context['attempt'].id}",
            )
        except TransformerStageError as error:
            raise DependencyTransitionError(error.code, error.message) from error
        return "queued"

    def _phase_install(self, session, continuation, context) -> str:
        key = f"{context['attempt'].id}:transition:install"
        execution = self._execution(session, context, key)
        if execution is None:
            return self._queue_transition_command(session, continuation, context, "install", key)
        if execution.status in {"pending", "queued", "running"}:
            self._stage._wait_for_command(session, continuation, execution.id)
            return "waiting"
        if execution.status != "succeeded" or execution.exit_code != 0:
            raise DependencyTransitionError(
                execution.failure_code or "DEPENDENCY_TRANSITION_COMMAND_FAILED",
                execution.failure_message or "npm install did not succeed",
            )
        self._verify_install(session, continuation, context, execution)
        return "continue"

    def _verify_install(self, session, continuation, context, execution) -> None:
        run = context["run"]
        binding = context["binding"]
        workspace = context["workspace"]
        intent = context["intent"]
        package = intent["blocking_package"]
        target_version = intent["target_version"]
        package_doc = self._read_package_json(workspace)
        range_value = None
        for section in ("dependencies", "devDependencies"):
            value = (package_doc.get(section) or {}).get(package)
            if isinstance(value, str):
                range_value = value
                break
        installed = workspace / "node_modules" / package / "package.json"
        installed_version = None
        if installed.is_file():
            try:
                installed_doc = json.loads(installed.read_text(encoding="utf-8"))
                installed_version = (
                    installed_doc.get("version")
                    if isinstance(installed_doc, dict)
                    else None
                )
            except (OSError, ValueError):
                installed_version = None
        if (
            range_value != target_version
            or installed_version != target_version
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INSTALL_VERIFICATION_FAILED",
                "npm install did not reattach the blocking dependency at the approved exact version",
            )
        post_binding = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
        dependency = _dependency_evidence(workspace, (package,))
        execution.end_fingerprint = {
            "canonical_source": post_binding,
            "dependency": dependency,
        }
        payload = {
            "schema_version": "dependency-transition-install-verification.v1",
            "execution_id": execution.id,
            "correlation_id": execution.correlation_id,
            "package": package,
            "target_version": intent["target_version"],
            "pre_command": execution.start_fingerprint or {},
            "post_command": {
                "package_json_sha256": _file_checksum(workspace / "package.json"),
                "manifest_range": range_value,
                "installed_version": installed_version,
            },
            "binding_fingerprint": binding.workspace_fingerprint,
            "dependency_evidence": dependency,
            "package_json_change": _package_json_change(
                (execution.start_fingerprint or {}).get("dependency"), dependency
            ),
            "lockfile_changes": {
                "before": ((execution.start_fingerprint or {}).get("dependency") or {}).get("lockfile_entries"),
                "after": dependency.get("lockfile_entries"),
            },
            "workspace_fingerprint": post_binding,
        }
        stored = self._write_or_recover_verification(
            session,
            run,
            continuation,
            f"{execution.id}.dependency-transition-install",
            payload,
        )
        self._register_verification_metadata(
            session,
            continuation,
            stored,
            execution_id=execution.id,
            owner_reference=f"{execution.id}:dependency-transition-install",
        )
        if post_binding != binding.workspace_fingerprint:
            self._update_binding_fingerprint(session, continuation, binding, post_binding)

    def _phase_ci(self, session, continuation, context) -> str:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "final_install-0",
            )
        )
        if step is not None and step.status == "PASSED":
            return "continue"
        execution = (
            session.get(CommandExecutionModel, step.execution_id)
            if step is not None and step.execution_id
            else None
        )
        if execution is None:
            try:
                result = self._stage._queue_group(
                    session,
                    continuation,
                    group="final_install",
                    next_node="dependency_transition",
                    attempt_key=f"{context['attempt'].id}:transition-ci",
                )
                queued = session.get(CommandExecutionModel, result.execution_id)
                planned_refs = (
                    ((context["stage_plan"].stage_plan or {}).get("commands") or {})
                    .get("final_install")
                    or []
                )
                planned = planned_refs[0] if len(planned_refs) == 1 else {}
                if queued is not None and isinstance(planned.get("timeout_seconds"), int):
                    queued.timeout_seconds = planned["timeout_seconds"]
            except TransformerStageError as error:
                raise DependencyTransitionError(error.code, error.message) from error
            return "queued"
        if execution.status in {"pending", "queued", "running"}:
            self._stage._wait_for_command(session, continuation, execution.id)
            return "waiting"
        if execution.status != "succeeded" or execution.exit_code != 0:
            raise DependencyTransitionError(
                execution.failure_code or "DEPENDENCY_TRANSITION_CI_FAILED",
                execution.failure_message or "npm ci did not succeed",
            )
        self._verify_ci(session, continuation, context, step, execution)
        return "continue"

    def _verify_ci(self, session, continuation, context, step, execution) -> None:
        run = context["run"]
        binding = context["binding"]
        workspace = context["workspace"]
        required_artifacts = (
            execution.stdout_artifact_id,
            execution.stderr_artifact_id,
            execution.command_log_artifact_id,
            execution.result_artifact_id,
            execution.manifest_artifact_id,
        )
        if (
            execution.command_id != "npm-ci-final"
            or any(not artifact_id for artifact_id in required_artifacts)
            or any(
                session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id)) is None
                for artifact_id in required_artifacts
            )
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_CI_EVIDENCE_INCOMPLETE",
                "npm ci command execution artifacts are incomplete",
            )
        post_binding = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
        dependency = _dependency_evidence(
            workspace, ("@angular/core", "@angular/cli", "@angular-devkit/build-angular")
        )
        execution.end_fingerprint = {
            "canonical_source": post_binding,
            "dependency": dependency,
        }
        payload = {
            "schema_version": "dependency-transition-ci-verification.v1",
            "execution_id": execution.id,
            "correlation_id": execution.correlation_id,
            "command": {
                "executable": execution.executable,
                "arguments": list(execution.arguments or []),
                "exit_code": execution.exit_code,
            },
            "post_workspace_fingerprint": post_binding,
            "dependency_evidence": dependency,
        }
        stored = self._write_or_recover_verification(
            session,
            run,
            continuation,
            f"{execution.id}.dependency-transition-ci",
            payload,
        )
        self._register_verification_metadata(
            session,
            continuation,
            stored,
            execution_id=execution.id,
            owner_reference=f"{execution.id}:dependency-transition-ci",
        )
        if post_binding != binding.workspace_fingerprint:
            self._update_binding_fingerprint(session, continuation, binding, post_binding)
        step.status = "PASSED"
        step.completed_at = self._now()
        step.workspace_fingerprint = post_binding
        step.updated_at = self._now()
        step.artifact_ids = list(
            dict.fromkeys([*(step.artifact_ids or []), stored.ref.artifact_id])
        )

    def _phase_closure(self, session, continuation, context) -> str:
        run = context["run"]
        attempt = context["attempt"]
        binding = context["binding"]
        workspace = context["workspace"]
        intent = context["intent"]
        if STAGE_FINGERPRINT_PROFILE.fingerprint(workspace) != binding.workspace_fingerprint:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_WORKSPACE_STALE",
                "The workspace no longer matches its active binding before closure verification",
            )
        report = verify_dependency_closure(
            workspace,
            target_major=intent["angular_major"],
            required_packages=(
                "@angular/core",
                "@angular/cli",
                "@angular/compiler-cli",
                intent["blocking_package"],
            ),
            exact_versions={intent["blocking_package"]: intent["target_version"]},
        )
        if not report["ok"]:
            raise DependencyTransitionError(
                "DEPENDENCY_CLOSURE_VIOLATION",
                "Dependency closure verification failed: "
                + json.dumps(report["violations"], sort_keys=True),
            )
        payload = {
            "schema_version": "dependency-transition-closure-verification.v1",
            "attempt_id": attempt.id,
            "target_major": intent["angular_major"],
            "report": report,
        }
        stored = self._write_or_recover_closure(session, run, continuation, attempt, payload)
        self._register_verification_metadata(
            session,
            continuation,
            stored,
            owner_reference=f"dependency-closure:{attempt.id}",
        )
        attempt.status = "applied_verified"
        attempt.completed_at = self._now()
        attempt.updated_at = self._now()
        self._resume(continuation, "verify_repair")
        return "passed"

    @staticmethod
    def _read_package_json(workspace: Path) -> dict[str, object]:
        try:
            document = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_PACKAGE_JSON_INVALID",
                "Workspace package.json is missing or invalid",
            ) from error
        return document if isinstance(document, dict) else {}

    def _update_binding_fingerprint(
        self, session, continuation, binding, new_fingerprint: str
    ) -> None:
        claimed = session.execute(
            update(StageWorkspaceBindingModel)
            .where(
                StageWorkspaceBindingModel.id == binding.id,
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
                StageWorkspaceBindingModel.workspace_fingerprint
                == binding.workspace_fingerprint,
            )
            .values(
                workspace_fingerprint=new_fingerprint,
                fingerprint_profile_id=STAGE_FINGERPRINT_PROFILE.profile_id,
                last_verified_fingerprint=new_fingerprint,
                last_verified_at=self._now(),
            )
        )
        if claimed.rowcount != 1:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_BINDING_STALE",
                "The active workspace binding changed during the dependency transition",
            )
        binding.workspace_fingerprint = new_fingerprint

    def _write_or_recover_verification(self, session, run, continuation, suffix, payload):
        content = json.dumps(payload, sort_keys=True, indent=2)
        checksum = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        store = LocalFilesystemArtifactStore(
            Path(str(run.artifact_root)).parent,
            fixed_run_root=Path(str(run.artifact_root)),
        )
        relative_path = f"04_workflow_state/command_executions/{suffix}.json"
        for ref in store.list_artifacts(run.id):
            if ref.relative_path == relative_path and ref.checksum == checksum:
                stored = store.read_artifact(run.id, ref.relative_path)
                if (
                    stored.envelope
                    and stored.envelope.input_hashes.get("execution")
                    == payload.get("execution_id")
                ):
                    return stored
        return store.write_text_artifact(
            run.id,
            relative_path,
            content,
            ArtifactType.JSON,
            stage_id=continuation.current_stage_id,
            created_by="dependency-transition-runner",
            created_at=self._now(),
            input_hashes={"execution": str(payload.get("execution_id") or "")},
            policy_version="dependency-transition-v1",
        )

    def _write_or_recover_closure(self, session, run, continuation, attempt, payload):
        content = json.dumps(payload, sort_keys=True, indent=2)
        checksum = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        store = LocalFilesystemArtifactStore(
            Path(str(run.artifact_root)).parent,
            fixed_run_root=Path(str(run.artifact_root)),
        )
        relative_path = (
            f"04_workflow_state/stages/{continuation.current_stage_id}/"
            f"dependency-closure/{attempt.id}.json"
        )
        for ref in store.list_artifacts(run.id):
            if ref.relative_path == relative_path and ref.checksum == checksum:
                stored = store.read_artifact(run.id, ref.relative_path)
                if (
                    stored.envelope
                    and stored.envelope.input_hashes.get("attempt") == attempt.id
                ):
                    return stored
        return store.write_text_artifact(
            run.id,
            relative_path,
            content,
            ArtifactType.JSON,
            stage_id=continuation.current_stage_id,
            created_by="dependency-transition-runner",
            created_at=self._now(),
            input_hashes={"attempt": attempt.id},
            policy_version="dependency-transition-closure-v1",
        )

    def _register_verification_metadata(
        self,
        session,
        continuation,
        stored,
        *,
        execution_id=None,
        owner_reference=None,
    ) -> None:
        metadata_id = "metadata-" + stored.ref.artifact_id
        if session.get(ArtifactMetadataModel, metadata_id) is not None:
            return
        session.add(
            ArtifactMetadataModel(
                id=metadata_id,
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                schema_version=stored.envelope.schema_version,
                created_at=stored.ref.created_at,
                execution_id=execution_id,
                owner_reference=owner_reference,
                mime_type=stored.envelope.content_type,
                size_bytes=len(stored.content.encode("utf-8")),
                finalized_at=stored.ref.created_at,
                immutable=True,
            )
        )

    def _resume(self, continuation, next_node: str) -> None:
        continuation.status = "queued"
        continuation.current_node = next_node
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.waiting_execution_id = None
        continuation.state_version += 1
        continuation.updated_at = self._now()
