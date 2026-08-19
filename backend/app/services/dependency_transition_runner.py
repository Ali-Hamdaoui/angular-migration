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
    NPM_DEPENDENCY_MATERIALIZE_RENDERER,
    NPM_DEPENDENCY_INSTALL_RENDERER,
    NPM_DEPENDENCY_UNINSTALL_RENDERER,
    TRANSFORMATION_COMMAND_CATALOGUE,
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
    compatible_reinstall_bundle,
    compatible_reinstall_version,
    is_exact_version,
    verify_dependency_closure,
    verify_dependency_transition_evidence_for_source,
)
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.lockfile_generation_runner import (
    LockfileGenerationError,
    validate_generated_lockfile,
    workspace_excluding_governed_volatile_fingerprint,
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
        if phase == "materialize_initial":
            outcome = self._phase_materialize(session, continuation, context, "initial")
        elif phase == "fresh_angular_update":
            outcome = self._phase_update_command(
                session, continuation, context, "fresh", fresh_evidence=True
            )
        elif phase == "materialize_transition":
            outcome = self._phase_materialize(session, continuation, context, "transition")
        elif phase == "uninstall":
            outcome = self._phase_uninstall(session, continuation, context)
        elif phase == "lockfile_detached":
            outcome = self._phase_lockfile(session, continuation, context, "detached")
        elif phase == "materialize_detached":
            outcome = self._phase_materialize(session, continuation, context, "detached")
        elif phase == "angular_update":
            outcome = self._phase_update_command(
                session, continuation, context, "detached", fresh_evidence=False
            )
        elif phase == "reinstall":
            outcome = self._phase_install(session, continuation, context)
        elif phase == "lockfile_final":
            outcome = self._phase_lockfile(session, continuation, context, "final")
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
        initial = self._latest_materialization_execution(session, context, "initial")
        if not self._verified(session, initial, "dependency-materialization"):
            return "materialize_initial"
        fresh = self._execution(session, context, self._key(context, "angular-update:fresh"))
        if fresh is None or fresh.status in {"pending", "queued", "running"}:
            return "fresh_angular_update"
        if fresh.status == "succeeded" and fresh.exit_code == 0:
            lockfile = self._execution(session, context, self._key(context, "lockfile:final"))
            if not self._verified(session, lockfile, "dependency-lockfile"):
                return "lockfile_final"
            return self._final_phase(session, continuation, context)
        if not self._has_evidence(session, fresh, "fresh-angular-update-failure"):
            return "fresh_angular_update"
        transition = self._latest_materialization_execution(session, context, "transition")
        if not self._verified(session, transition, "dependency-materialization"):
            return "materialize_transition"
        uninstall = self._execution(session, context, self._key(context, "uninstall"))
        uninstall_verified = uninstall is not None and session.scalar(
            select(ArtifactMetadataModel.id).where(
                ArtifactMetadataModel.owner_reference
                == f"{uninstall.id}:dependency-transition-uninstall"
            )
        )
        if uninstall is None or uninstall.status != "succeeded" or not uninstall_verified:
            return "uninstall"
        detached_lock = self._execution(
            session, context, self._key(context, "lockfile:detached")
        )
        if not self._verified(session, detached_lock, "dependency-lockfile"):
            return "lockfile_detached"
        detached_materialization = self._execution(
            session, context, self._key(context, "materialize:detached")
        )
        if not self._verified(
            session, detached_materialization, "dependency-materialization"
        ):
            return "materialize_detached"
        angular = self._execution(
            session, context, self._key(context, "angular-update:detached")
        )
        if angular is None or angular.status != "succeeded" or angular.exit_code != 0:
            return "angular_update"
        install = self._latest_install_execution(session, context)
        install_verified = install is not None and session.scalar(
            select(ArtifactMetadataModel.id).where(
                ArtifactMetadataModel.owner_reference
                == f"{install.id}:dependency-transition-install"
            )
        )
        if install is None or install.status != "succeeded" or not install_verified:
            return "reinstall"
        final_lock = self._execution(session, context, self._key(context, "lockfile:final"))
        if not self._verified(session, final_lock, "dependency-lockfile"):
            return "lockfile_final"
        return self._final_phase(session, continuation, context)

    def _final_phase(self, session, continuation, context) -> str:
        ci_step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "final_install-0",
            )
        )
        ci_execution = (
            session.get(CommandExecutionModel, ci_step.execution_id)
            if ci_step is not None and ci_step.execution_id
            else None
        )
        final_lock = self._execution(
            session, context, self._key(context, "lockfile:final")
        )
        fresh_ci = bool(
            ci_step is not None
            and ci_step.status == "PASSED"
            and ci_execution is not None
            and ci_execution.status == "succeeded"
            and final_lock is not None
            and (ci_execution.requested_at or self._now())
            > (final_lock.finished_at or final_lock.requested_at)
        )
        return "dependency_closure" if fresh_ci else "npm_ci"

    @staticmethod
    def _key(context, suffix: str) -> str:
        return f"{context['attempt'].id}:transition:v2:{suffix}"

    @staticmethod
    def _verified(session, execution, owner_suffix: str) -> bool:
        return bool(
            execution is not None
            and execution.status == "succeeded"
            and execution.exit_code == 0
            and session.scalar(
                select(ArtifactMetadataModel.id).where(
                    ArtifactMetadataModel.owner_reference
                    == f"{execution.id}:{owner_suffix}"
                )
            )
        )

    @staticmethod
    def _has_evidence(session, execution, owner_suffix: str) -> bool:
        return bool(
            execution is not None
            and session.scalar(
                select(ArtifactMetadataModel.id).where(
                    ArtifactMetadataModel.owner_reference
                    == f"{execution.id}:{owner_suffix}"
                )
            )
        )

    def requires_safe_restore(self, session, continuation) -> bool:
        """Return whether the next materialization lacks a restored-state proof."""
        attempt = session.scalar(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
        )
        if attempt is None:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_AUTHORITY_MISSING",
                "Dependency-transition repair attempt is missing",
            )

        def execution(suffix: str):
            return session.scalar(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.idempotency_key
                    == f"{attempt.id}:transition:v2:{suffix}",
                )
            )

        context = {"run": session.get(MigrationRunModel, continuation.run_id), "attempt": attempt}
        initial = self._latest_materialization_execution(session, context, "initial")
        if initial is None:
            return True
        if initial.status in {"succeeded", "failed", "timed_out", "cancelled"}:
            runtime = self._stage.runtime_binding(session, continuation)
            start = initial.start_fingerprint or {}
            if (
                initial.runtime_checksum != runtime["checksum"]
                or start.get("runtime_checksum") != runtime["checksum"]
                or start.get("runtime_profile_id") != runtime["profile_id"]
            ):
                return True
        fresh = execution("angular-update:fresh")
        transition = execution("materialize:transition")
        binding = self._stage._binding(session, continuation)
        if (
            fresh is not None
            and fresh.status == "failed"
            and self._has_evidence(session, fresh, "fresh-angular-update-failure")
            and (fresh.start_fingerprint or {}).get("binding_fingerprint")
            == binding.workspace_fingerprint
        ):
            live = STAGE_FINGERPRINT_PROFILE.fingerprint(Path(binding.workspace_path))
            fresh.end_fingerprint = {"canonical_source": live}
            if live != binding.workspace_fingerprint:
                self._update_binding_fingerprint(
                    session, continuation, binding, live
                )
        return bool(
            fresh is not None
            and fresh.status == "failed"
            and self._has_evidence(session, fresh, "fresh-angular-update-failure")
            and transition is None
        )

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
        intent["evidence_diagnosis"] = self._evidence_diagnosis(
            session, continuation, run, attempt
        )
        return {
            "run": run,
            "attempt": attempt,
            "binding": binding,
            "workspace": workspace,
            "stage_plan": stage_plan,
            "plan": plan,
            "intent": intent,
        }

    @staticmethod
    def _evidence_diagnosis(session, continuation, run, attempt) -> dict[str, object]:
        if not attempt.failure_evidence_artifact_id or not attempt.failure_evidence_checksum:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_EVIDENCE_INVALID",
                "Dependency-transition failure evidence is missing",
            )
        metadata = session.get(
            ArtifactMetadataModel,
            "metadata-" + str(attempt.failure_evidence_artifact_id),
        )
        if metadata is None or metadata.checksum != attempt.failure_evidence_checksum:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_EVIDENCE_INVALID",
                "Dependency-transition failure evidence binding is stale",
            )
        try:
            stored = LocalFilesystemArtifactStore(
                Path(str(run.artifact_root)).parent,
                fixed_run_root=Path(str(run.artifact_root)),
            ).read_artifact(continuation.run_id, metadata.relative_path)
            if (
                stored.ref.artifact_id != attempt.failure_evidence_artifact_id
                or stored.ref.checksum != attempt.failure_evidence_checksum
            ):
                raise ValueError("Dependency-transition failure evidence identity changed")
            evidence, diagnosis = FailureEvidenceService.normalize_dependency_transition_evidence(
                json.loads(stored.content)
            )
            if not isinstance(evidence, dict) or not isinstance(diagnosis, dict):
                raise ValueError("Dependency-transition failure diagnosis is missing")
            return diagnosis
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, TypeError, ValueError) as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_EVIDENCE_INVALID", str(error)
            ) from error

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
                str(blocking_package or ""),
                int(angular_major) if isinstance(angular_major, int) else -1,
                required_ranges=peer_ranges,
                installed_version=installed_version,
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
        try:
            bundle = compatible_reinstall_bundle(
                str(blocking_package),
                int(angular_major),
                workspace,
                required_ranges=peer_ranges,
                installed_version=installed_version,
            )
        except ValueError as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INTENT_INVALID", str(error)
            ) from error
        transition_targets = [
            {
                "package": member.package,
                "exact_version": member.exact_version,
                "required": member.required,
            }
            for member in bundle.members
        ]
        if (
            not transition_targets
            or transition_targets[-1]["package"] != blocking_package
            or transition_targets[-1]["exact_version"] != approved_target_version
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INTENT_INVALID",
                "dependency_transition transition bundle is inconsistent with backend authority",
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
            or not planned.get("template_id")
            or not isinstance(planned.get("template_version"), int)
            or planned.get("executable") != "npx"
            or not isinstance(planned.get("arguments"), list)
            or any(
                forbidden in (planned.get("arguments") or [])
                for forbidden in ("--force", "--legacy-peer-deps", "--allow-dirty")
            )
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
            "transition_targets": transition_targets,
            "target_exact": str(target_exact or ""),
            "target_cli_exact": str(target_cli_exact or ""),
            "angular_command": {
                "command_id": planned["command_id"],
                "template_id": planned["template_id"],
                "template_version": planned["template_version"],
                "executable": planned["executable"],
                "arguments": list(planned["arguments"]),
                "network_profile": planned.get("network_profile")
                or "approved-registries-only",
                "timeout_seconds": planned.get("timeout_seconds") or 1800,
            },
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

    def _install_executions(self, session, context) -> list:
        """All reattach executions for this repair attempt in durable order.

        Covers member-scoped keys
        (``{attempt}:transition:install:{index}:{package}:attempt-N``), dynamic
        generations (``{attempt}:transition:install:attempt-N``), and historical
        keys (``{attempt}:transition:install`` and ``{attempt}:transition:install-v3``)
        which are read for resume compatibility but never written again.
        """
        prefix = self._key(context, "install")
        executions = list(
            session.scalars(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == context["run"].id,
                    CommandExecutionModel.idempotency_key.startswith(prefix),
                )
            )
        )
        executions.sort(key=lambda execution: (execution.requested_at, execution.id))
        return executions

    def _latest_install_execution(self, session, context):
        executions = self._install_executions(session, context)
        return executions[-1] if executions else None

    def _member_install_prefix(self, context, member_index: int) -> str:
        targets = context["intent"]["transition_targets"]
        base = self._key(context, "install")
        if len(targets) == 1:
            return base
        return f"{base}:{member_index}:{targets[member_index]['package'].replace('/', '_')}"

    def _latest_member_install(self, session, context, member_prefix: str):
        executions = [
            execution
            for execution in self._install_executions(session, context)
            if (execution.idempotency_key or "").startswith(member_prefix)
        ]
        return executions[-1] if executions else None

    def _next_install_key(self, session, context, member_prefix: str) -> str:
        generation = 1
        pattern = re.compile(re.escape(member_prefix) + r":attempt-([1-9][0-9]*)$")
        for key in self._consumed_idempotency_keys(
            session, context, member_prefix, pattern
        ):
            match = pattern.fullmatch(key)
            if match is not None:
                generation = max(generation, int(match.group(1)) + 1)
        return f"{member_prefix}:attempt-{generation}"

    def _phase_materialize(self, session, continuation, context, generation: str) -> str:
        key = self._key(context, f"materialize:{generation}")
        execution = self._latest_materialization_execution(session, context, generation)
        if execution is None:
            try:
                validate_generated_lockfile(context["workspace"])
            except LockfileGenerationError as error:
                raise DependencyTransitionError(
                    "DEPENDENCY_MATERIALIZATION_FAILED", error.message
                ) from error
            return self._queue_transition_command(
                session, continuation, context, "materialize", key
            )
        if execution.status in {"pending", "queued", "running"}:
            self._stage._wait_for_command(session, continuation, execution.id)
            return "waiting"
        if execution.status != "succeeded" or execution.exit_code != 0:
            if self._retryable_prelaunch_failure(session, context, generation, execution):
                retry_key = self._next_materialization_key(session, context, generation)
                return self._queue_transition_command(
                    session, continuation, context, "materialize", retry_key
                )
            raise DependencyTransitionError(
                execution.failure_code or "DEPENDENCY_MATERIALIZATION_FAILED",
                execution.failure_message or "Checkpoint dependency state cannot be materialized with npm ci",
            )
        if not self._command_evidence_complete(session, execution):
            raise DependencyTransitionError(
                "DEPENDENCY_MATERIALIZATION_EVIDENCE_INVALID",
                "npm ci terminal evidence is incomplete",
            )
        try:
            self._verify_materialization(session, continuation, context, execution)
        except DependencyTransitionError as error:
            if error.code != "DEPENDENCY_MATERIALIZATION_EVIDENCE_INVALID":
                raise
            retry_key = self._next_materialization_key(session, context, generation)
            return self._queue_transition_command(
                session, continuation, context, "materialize", retry_key
            )
        return "continue"

    def _retryable_prelaunch_failure(self, session, context, generation: str, execution) -> bool:
        """Allow one durable successor when the Factory failed before spawning npm."""
        if (
            execution.status != "failed"
            or execution.process_id is not None
            or execution.exit_code is not None
            or any(
                (
                    execution.stdout_artifact_id,
                    execution.stderr_artifact_id,
                    execution.command_log_artifact_id,
                    execution.result_artifact_id,
                    execution.manifest_artifact_id,
                )
            )
        ):
            return False
        return not any(
            candidate.id != execution.id
            and candidate.status == "failed"
            and candidate.process_id is None
            and candidate.exit_code is None
            for candidate in self._materialization_executions(
                session, context, generation
            )
        )

    def _verify_materialization(self, session, continuation, context, execution) -> None:
        workspace = context["workspace"]
        start = execution.start_fingerprint or {}
        runtime = self._stage.runtime_binding(session, continuation)
        required_artifacts = (
            execution.stdout_artifact_id,
            execution.stderr_artifact_id,
            execution.command_log_artifact_id,
            execution.result_artifact_id,
            execution.manifest_artifact_id,
        )
        if (
            execution.command_id != NPM_DEPENDENCY_MATERIALIZE_RENDERER.command_id
            or list(execution.arguments or []) != ["ci"]
            or execution.runtime_checksum != runtime["checksum"]
            or start.get("runtime_checksum") != runtime["checksum"]
            or start.get("runtime_profile_id") != runtime["profile_id"]
            or _file_checksum(workspace / "package.json") != start.get("package_json_sha256")
            or _file_checksum(workspace / "package-lock.json") != start.get("package_lock_sha256")
            or _file_checksum(workspace / ".npmrc") != start.get("npmrc_sha256")
            or any(not artifact_id for artifact_id in required_artifacts)
            or any(
                session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id)) is None
                for artifact_id in required_artifacts
            )
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_MATERIALIZATION_EVIDENCE_INVALID",
                "npm ci materialization is not bound to the manifest, lockfile, npm configuration, and exact stage runtime",
            )
        try:
            lock_status = validate_generated_lockfile(workspace)
        except LockfileGenerationError as error:
            raise DependencyTransitionError(
                "DEPENDENCY_MATERIALIZATION_FAILED", error.message
            ) from error
        payload = {
            "schema_version": "dependency-materialization-verification.v1",
            "execution_id": execution.id,
            "attempt_id": context["attempt"].id,
            "command": {"arguments": list(execution.arguments or []), "exit_code": execution.exit_code},
            "package_json_sha256": start["package_json_sha256"],
            "package_lock_sha256": start["package_lock_sha256"],
            "npmrc_sha256": start["npmrc_sha256"],
            "runtime_profile_id": runtime["profile_id"],
            "runtime_checksum": runtime["checksum"],
            "lockfile_status": lock_status,
            "artifact_ids": list(required_artifacts),
        }
        stored = self._write_or_recover_verification(
            session, context["run"], continuation, f"{execution.id}.dependency-materialization", payload
        )
        self._register_verification_metadata(
            session,
            continuation,
            stored,
            execution_id=execution.id,
            owner_reference=f"{execution.id}:dependency-materialization",
        )
        execution.end_fingerprint = dict(start)

    def _phase_lockfile(self, session, continuation, context, generation: str) -> str:
        key = self._key(context, f"lockfile:{generation}")
        execution = self._execution(session, context, key)
        if execution is None:
            return self._queue_transition_command(
                session, continuation, context, "lockfile", key
            )
        if execution.status in {"pending", "queued", "running"}:
            self._stage._wait_for_command(session, continuation, execution.id)
            return "waiting"
        if execution.status != "succeeded" or execution.exit_code != 0:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_LOCKFILE_FAILED",
                execution.failure_message or "Generic npm lockfile reconciliation failed",
            )
        self._verify_lockfile(session, continuation, context, execution)
        return "continue"

    def _verify_lockfile(self, session, continuation, context, execution) -> None:
        workspace = context["workspace"]
        start = execution.start_fingerprint or {}
        runtime = self._stage.runtime_binding(session, continuation)
        required_artifacts = (
            execution.stdout_artifact_id,
            execution.stderr_artifact_id,
            execution.command_log_artifact_id,
            execution.result_artifact_id,
            execution.manifest_artifact_id,
        )
        if (
            execution.command_id != "npm-lockfile-generate"
            or list(execution.arguments or [])
            != ["install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"]
            or execution.runtime_checksum != runtime["checksum"]
            or start.get("runtime_checksum") != runtime["checksum"]
            or start.get("runtime_profile_id") != runtime["profile_id"]
            or _file_checksum(workspace / "package.json") != start.get("package_json_sha256")
            or _file_checksum(workspace / ".npmrc") != start.get("npmrc_sha256")
            or workspace_excluding_governed_volatile_fingerprint(workspace)
            != start.get("workspace_without_lockfile")
            or any(not artifact_id for artifact_id in required_artifacts)
            or any(
                session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id)) is None
                for artifact_id in required_artifacts
            )
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_LOCKFILE_EVIDENCE_INVALID",
                "Generic lockfile reconciliation changed unauthorized state or lacks exact runtime evidence",
            )
        try:
            lock_status = validate_generated_lockfile(workspace)
        except LockfileGenerationError as error:
            raise DependencyTransitionError(error.code, error.message) from error
        live = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
        payload = {
            "schema_version": "dependency-transition-lockfile-verification.v1",
            "execution_id": execution.id,
            "attempt_id": context["attempt"].id,
            "package_json_sha256": start["package_json_sha256"],
            "package_lock_sha256": _file_checksum(workspace / "package-lock.json"),
            "npmrc_sha256": start["npmrc_sha256"],
            "runtime_checksum": runtime["checksum"],
            "lockfile_status": lock_status,
            "workspace_fingerprint": live,
        }
        stored = self._write_or_recover_verification(
            session, context["run"], continuation, f"{execution.id}.dependency-lockfile", payload
        )
        self._register_verification_metadata(
            session,
            continuation,
            stored,
            execution_id=execution.id,
            owner_reference=f"{execution.id}:dependency-lockfile",
        )
        execution.end_fingerprint = payload
        if live != context["binding"].workspace_fingerprint:
            self._update_binding_fingerprint(
                session, continuation, context["binding"], live
            )

    def _phase_update_command(
        self, session, continuation, context, generation: str, *, fresh_evidence: bool
    ) -> str:
        key = self._key(context, f"angular-update:{generation}")
        execution = self._execution(session, context, key)
        if execution is None:
            return self._queue_transition_command(
                session, continuation, context, "angular_update", key
            )
        if execution.status in {"pending", "queued", "running"}:
            self._stage._wait_for_command(session, continuation, execution.id)
            return "waiting"
        if not self._command_evidence_complete(session, execution):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_ANGULAR_EVIDENCE_MISSING",
                "Angular update terminal evidence is incomplete",
            )
        if execution.status == "succeeded" and execution.exit_code == 0:
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.run_id == continuation.run_id,
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "angular_update-0",
                )
            )
            live = STAGE_FINGERPRINT_PROFILE.fingerprint(context["workspace"])
            execution.end_fingerprint = {"canonical_source": live}
            if step is not None:
                step.execution_id = execution.id
                step.status = "PASSED"
                step.completed_at = self._now()
                step.workspace_fingerprint = live
                step.updated_at = self._now()
            if live != context["binding"].workspace_fingerprint:
                self._update_binding_fingerprint(
                    session, continuation, context["binding"], live
                )
            return "continue"
        if not fresh_evidence:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_ANGULAR_UPDATE_FAILED",
                execution.failure_message or "Angular update failed after dependency detach",
            )
        self._record_fresh_failure(session, continuation, context, execution)
        return "continue"

    @staticmethod
    def _command_evidence_complete(session, execution) -> bool:
        artifact_ids = (
            execution.stdout_artifact_id,
            execution.stderr_artifact_id,
            execution.command_log_artifact_id,
            execution.result_artifact_id,
            execution.manifest_artifact_id,
        )
        return bool(
            all(artifact_ids)
            and all(
                session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))
                is not None
                for artifact_id in artifact_ids
            )
        )

    def _materialization_executions(self, session, context, generation: str) -> list:
        prefix = self._key(context, f"materialize:{generation}")
        executions = list(
            session.scalars(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == context["run"].id,
                    CommandExecutionModel.idempotency_key.startswith(prefix),
                )
            )
        )
        executions.sort(key=lambda execution: (execution.requested_at, execution.id))
        return executions

    def _latest_materialization_execution(self, session, context, generation: str):
        executions = self._materialization_executions(session, context, generation)
        return executions[-1] if executions else None

    def _consumed_idempotency_keys(
        self, session, context, prefix: str, pattern: re.Pattern[str]
    ) -> set[str]:
        """Return strictly shaped keys reserved by authorization or execution."""
        run_id = context["run"].id
        stage_id = context["attempt"].stage_id
        keys: set[str] = set()
        for model in (CommandExecutionModel, CommandAuthorizationAuditModel):
            keys.update(
                key
                for key in session.scalars(
                    select(model.idempotency_key).where(
                        model.run_id == run_id,
                        model.stage_id == stage_id,
                        model.idempotency_key.startswith(prefix),
                    )
                )
                if isinstance(key, str) and pattern.fullmatch(key)
            )
        return keys

    def _next_materialization_key(self, session, context, generation: str) -> str:
        base = self._key(context, f"materialize:{generation}")
        retry = 1
        pattern = re.compile(re.escape(base) + r"(?::retry-([1-9][0-9]*))?$")
        for key in self._consumed_idempotency_keys(session, context, base, pattern):
            match = pattern.fullmatch(key)
            if match is not None and match.group(1) is not None:
                retry = max(retry, int(match.group(1)) + 1)
        return f"{base}:retry-{retry}"

    def _record_fresh_failure(self, session, continuation, context, execution) -> None:
        normalized = {
            "error_code": execution.failure_code or "ANGULAR_UPDATE_FAILED",
            "command_id": execution.command_id,
            "exit_code": execution.exit_code,
            "failure_code": execution.failure_code,
            "failure_message": (execution.failure_message or "")[:2000],
            "command_allows_dirty": "--allow-dirty" in (execution.arguments or []),
        }
        diagnosis = FailureEvidenceService.diagnose_angular_update_failure(normalized)
        normalized["failure_diagnosis"] = diagnosis
        approved = context["intent"]["evidence_diagnosis"]
        matches = not (
            not isinstance(diagnosis, dict)
            or diagnosis.get("kind") != "peer_dependency_conflict"
            or context["intent"]["blocking_package"]
            not in dict(diagnosis.get("required_ranges") or {})
            or dict(diagnosis.get("required_ranges") or {})
            != dict(context["intent"]["peer_ranges"])
        )
        payload = {
            "schema_version": "dependency-transition-fresh-failure.v1",
            "execution_id": execution.id,
            "attempt_id": context["attempt"].id,
            "approved_failure_artifact_id": context["attempt"].failure_evidence_artifact_id,
            "approved_diagnosis": approved,
            "normalized_failure": normalized,
            "artifact_ids": list(execution.artifact_ids or []),
            "matches_approved_blocker": matches,
        }
        suffix = (
            "fresh-angular-update-failure"
            if matches
            else "fresh-angular-update-blocker-changed"
        )
        stored = self._write_or_recover_verification(
            session, context["run"], continuation, f"{execution.id}.{suffix}", payload
        )
        self._register_verification_metadata(
            session,
            continuation,
            stored,
            execution_id=execution.id,
            owner_reference=f"{execution.id}:{suffix}",
        )
        if not matches:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_FRESH_BLOCKER_CHANGED",
                "The restored Angular update produced a different blocker; stale repair evidence cannot authorize mutation",
            )

    def _phase_uninstall(self, session, continuation, context) -> str:
        key = self._key(context, "uninstall")
        execution = self._execution(session, context, key)
        if execution is None:
            try:
                verify_dependency_transition_evidence_for_source(
                    context["workspace"],
                    diagnosis=self._fresh_failure_diagnosis(session, context),
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

    def _fresh_failure_diagnosis(self, session, context) -> dict[str, object]:
        execution = self._execution(
            session, context, self._key(context, "angular-update:fresh")
        )
        metadata = (
            session.scalar(
                select(ArtifactMetadataModel).where(
                    ArtifactMetadataModel.owner_reference
                    == f"{execution.id}:fresh-angular-update-failure"
                )
            )
            if execution is not None
            else None
        )
        if metadata is None:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_FRESH_EVIDENCE_MISSING",
                "Fresh Angular update failure evidence is missing",
            )
        try:
            stored = LocalFilesystemArtifactStore(
                Path(str(context["run"].artifact_root)).parent,
                fixed_run_root=Path(str(context["run"].artifact_root)),
            ).read_artifact(context["run"].id, metadata.relative_path)
            payload = json.loads(stored.content)
            _, diagnosis = FailureEvidenceService.normalize_dependency_transition_evidence(
                payload
            )
            if (
                stored.ref.artifact_id != metadata.id.removeprefix("metadata-")
                or stored.ref.checksum != metadata.checksum
                or stored.envelope is None
                or stored.envelope.run_id != context["run"].id
                or stored.envelope.stage_id != context["attempt"].stage_id
                or stored.envelope.input_hashes.get("execution") != execution.id
                or not isinstance(diagnosis, dict)
            ):
                raise ValueError("Fresh dependency diagnosis binding is invalid")
            return diagnosis
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, TypeError, ValueError) as error:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_FRESH_EVIDENCE_INVALID", str(error)
            ) from error

    def _queue_transition_command(
        self, session, continuation, context, phase, key, member=None
    ) -> str:
        run = context["run"]
        attempt = context["attempt"]
        binding = context["binding"]
        workspace = context["workspace"]
        intent = context["intent"]
        npmrc = workspace / ".npmrc"
        npmrc_text = (
            npmrc.read_text(encoding="utf-8", errors="replace").casefold()
            if npmrc.is_file()
            else ""
        )
        if "legacy-peer-deps=true" in npmrc_text or "force=true" in npmrc_text:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_NPM_CONFIG_FORBIDDEN",
                "Dependency transition forbids force and legacy-peer-deps npm configuration",
            )
        template_version = 1
        if phase == "materialize":
            renderer = NPM_DEPENDENCY_MATERIALIZE_RENDERER
            bindings = {}
        elif phase == "lockfile":
            renderer = TRANSFORMATION_COMMAND_CATALOGUE["npm-lockfile-generate"]
            bindings = {}
        elif phase == "angular_update":
            command = intent["angular_command"]
            renderer = None
            bindings = {}
            template_version = command["template_version"]
        elif phase == "uninstall":
            renderer = NPM_DEPENDENCY_UNINSTALL_RENDERER
            bindings = {"package": intent["blocking_package"]}
        else:
            renderer = NPM_DEPENDENCY_INSTALL_RENDERER
            member = member or {
                "package": intent["blocking_package"],
                "exact_version": intent["target_version"],
            }
            bindings = {
                "package": member["package"],
                "target_version": member["exact_version"],
            }
        try:
            arguments = (
                list(command["arguments"])
                if phase == "angular_update"
                else list(renderer.render_arguments(bindings))
            )
            authorization_id = self._command_executor.authorize_dependency_transition_command(
                session,
                attempt_id=attempt.id,
                command_id=(command["command_id"] if phase == "angular_update" else renderer.command_id),
                template_id=(command["template_id"] if phase == "angular_update" else renderer.template_id),
                template_version=template_version,
                executable=(command["executable"] if phase == "angular_update" else renderer.executable),
                arguments=arguments,
                working_directory_alias=binding.alias,
                working_directory=binding.workspace_path,
                plan_id=intent["plan_id"],
                plan_version=intent["plan_version"],
                execution_profile_id=intent["execution_profile_id"],
                network_profile=(command["network_profile"] if phase == "angular_update" else renderer.network_profile),
                timeout_seconds=(command["timeout_seconds"] if phase == "angular_update" else renderer.timeout_seconds),
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
                timeout_seconds=(command["timeout_seconds"] if phase == "angular_update" else renderer.timeout_seconds),
            )
        except CommandExecutorError as error:
            raise DependencyTransitionError(error.code, error.message) from error
        execution = session.get(CommandExecutionModel, result.execution_id)
        if execution is None:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_QUEUE_FAILED",
                "Queued transition command evidence is missing",
            )
        evidence_package = member["package"] if member is not None else intent["blocking_package"]
        dependency = _dependency_evidence(workspace, (evidence_package,))
        runtime = self._stage.runtime_binding(session, continuation)
        execution.start_fingerprint = {
            "canonical_source": binding.workspace_fingerprint,
            "dependency": dependency,
            "package_json_sha256": _file_checksum(workspace / "package.json"),
            "package_lock_sha256": _file_checksum(workspace / "package-lock.json"),
            "npmrc_sha256": _file_checksum(workspace / ".npmrc"),
            "runtime_profile_id": runtime["profile_id"],
            "runtime_checksum": runtime["checksum"],
            f"node_modules_{evidence_package.replace('/', '_')}_package_json_sha256": (
                _file_checksum(workspace / "node_modules" / evidence_package / "package.json")
            ),
            "binding_fingerprint": binding.workspace_fingerprint,
        }
        if phase == "lockfile":
            execution.start_fingerprint["workspace_without_lockfile"] = (
                workspace_excluding_governed_volatile_fingerprint(workspace)
            )
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
        if manifest_has:
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_UNINSTALL_VERIFICATION_FAILED",
                "npm uninstall left the blocking dependency in package.json",
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

    def _phase_install(self, session, continuation, context) -> str:
        targets = context["intent"]["transition_targets"]
        for member_index, member in enumerate(targets):
            member_prefix = self._member_install_prefix(context, member_index)
            latest = self._latest_member_install(session, context, member_prefix)
            if latest is None:
                return self._queue_transition_command(
                    session,
                    continuation,
                    context,
                    "install",
                    self._next_install_key(session, context, member_prefix),
                    member=member,
                )
            if latest.status in {"pending", "queued", "running"}:
                self._stage._wait_for_command(session, continuation, latest.id)
                return "waiting"
            if latest.status == "succeeded" and latest.exit_code == 0:
                self._verify_install(session, continuation, context, latest, member)
                continue
            raise DependencyTransitionError(
                latest.failure_code or "DEPENDENCY_TRANSITION_COMMAND_FAILED",
                latest.failure_message or "npm install did not succeed",
            )
        return "continue"

    def _verify_install(self, session, continuation, context, execution, member) -> None:
        run = context["run"]
        binding = context["binding"]
        workspace = context["workspace"]
        package = member["package"]
        target_version = member["exact_version"]
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
        dependency = _dependency_evidence(workspace, (package,))
        lockfile_version = (
            ((dependency.get("lockfile_entries") or {}).get(package) or {}).get("version")
        )
        if (
            range_value != target_version
            or lockfile_version != target_version
            or installed_version != target_version
        ):
            raise DependencyTransitionError(
                "DEPENDENCY_TRANSITION_INSTALL_VERIFICATION_FAILED",
                "npm install did not install the transition target at the approved exact version",
            )
        post_binding = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
        execution.end_fingerprint = {
            "canonical_source": post_binding,
            "dependency": dependency,
        }
        payload = {
            "schema_version": "dependency-transition-install-verification.v1",
            "execution_id": execution.id,
            "correlation_id": execution.correlation_id,
            "package": package,
            "target_version": target_version,
            "pre_command": execution.start_fingerprint or {},
            "post_command": {
                "package_json_sha256": _file_checksum(workspace / "package.json"),
                "manifest_range": range_value,
                "lockfile_version": lockfile_version,
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
        execution = (
            session.get(CommandExecutionModel, step.execution_id)
            if step is not None and step.execution_id
            else None
        )
        final_lock = self._execution(
            session, context, self._key(context, "lockfile:final")
        )
        stale = bool(
            execution is None
            or final_lock is None
            or (execution.requested_at or self._now())
            <= (final_lock.finished_at or final_lock.requested_at)
        )
        if stale:
            try:
                result = self._stage._queue_group(
                    session,
                    continuation,
                    group="final_install",
                    next_node="dependency_transition",
                    attempt_key=f"dependency-transition-ci-{context['attempt'].id}",
                )
            except TransformerStageError as error:
                raise DependencyTransitionError(error.code, error.message) from error
            execution = session.get(CommandExecutionModel, result.execution_id)
            runtime = self._stage.runtime_binding(session, continuation)
            execution.start_fingerprint = {
                "package_json_sha256": _file_checksum(context["workspace"] / "package.json"),
                "package_lock_sha256": _file_checksum(context["workspace"] / "package-lock.json"),
                "npmrc_sha256": _file_checksum(context["workspace"] / ".npmrc"),
                "runtime_profile_id": runtime["profile_id"],
                "runtime_checksum": runtime["checksum"],
                "lockfile_execution_id": final_lock.id,
            }
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
        final_lock = self._execution(
            session, context, self._key(context, "lockfile:final")
        )
        if (
            execution.command_id != "npm-ci-final"
            or execution.runtime_checksum
            != self._stage.runtime_binding(session, continuation)["checksum"]
            or _file_checksum(workspace / "package.json")
            != (execution.start_fingerprint or {}).get("package_json_sha256")
            or _file_checksum(workspace / "package-lock.json")
            != (execution.start_fingerprint or {}).get("package_lock_sha256")
            or _file_checksum(workspace / ".npmrc")
            != (execution.start_fingerprint or {}).get("npmrc_sha256")
            or final_lock is None
            or not self._verified(session, final_lock, "dependency-lockfile")
            or (execution.start_fingerprint or {}).get("lockfile_execution_id")
            != final_lock.id
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
        transition_targets = intent["transition_targets"]
        report = verify_dependency_closure(
            workspace,
            target_major=intent["angular_major"],
            required_packages=(
                "@angular/core",
                "@angular/cli",
                "@angular/compiler-cli",
                *(target["package"] for target in transition_targets),
            ),
            exact_versions={
                target["package"]: target["exact_version"]
                for target in transition_targets
            },
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
