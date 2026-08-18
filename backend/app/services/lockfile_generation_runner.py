"""Post-G10 governed npm lockfile generation and verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.baseline import (
    BaselineQualificationError,
    LockfilePrequalificationService,
    PackageMetadataInspector,
)
from app.domain.contracts import ArtifactType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
)
from app.services.repair_application_service import RepairProposal
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE, STAGE_VOLATILE_NAMES

#: Governed mutation-scope identity for npm-lockfile-generate evidence.
#: v1 (pre-fix) fingerprint scope excluded only the root package-lock.json and
#: therefore treated npm's generated node_modules/.package-lock.json as an
#: unexpected mutation.  v2 excludes the root package-lock.json plus the same
#: volatile roots (node_modules/** and friends) the stage fingerprint system
#: already governs by, so npm's generated tree cannot raise false positives.
LOCKFILE_GENERATION_FINGERPRINT_SCOPE = "lockfile-generation-mutation-v2"

#: Deterministic durable attempt marker for the one V1 -> V2 successor
#: generation.  The successor idempotency key is derived from this suffix, so
#: restarts reconstruct the same key and never queue endless successors.
LOCKFILE_GENERATION_ATTEMPT_2_MARKER = ":attempt-2"
LOCKFILE_GENERATION_ETARGET = "LOCKFILE_GENERATION_ETARGET"
LOCKFILE_GENERATION_ERESOLVE = "LOCKFILE_GENERATION_ERESOLVE"

_NPM_ERROR_PREFIX = r"npm\s+(?:error|ERR!)"
_NPM_ETARGET_CODE = re.compile(
    rf"(?im)^\s*{_NPM_ERROR_PREFIX}\s+code\s+ETARGET\b"
)
_NPM_NO_MATCHING_VERSION = re.compile(
    rf"(?im)^\s*{_NPM_ERROR_PREFIX}\s+notarget\s+No matching version found for\s+\S+"
)
_NPM_ERESOLVE = re.compile(
    rf"(?im)^\s*(?:{_NPM_ERROR_PREFIX}|npm\s+WARN)\s+ERESOLVE\b"
    rf"|^\s*(?:{_NPM_ERROR_PREFIX}\s+)?(?:code\s+)?ERESOLVE\b"
)


class LockfileGenerationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_npm_etarget_failure(execution) -> bool:
    """Recognize only persisted npm ETARGET dependency-resolution evidence."""
    if (
        execution is None
        or execution.command_id != "npm-lockfile-generate"
        or execution.status != "failed"
        or execution.exit_code in (None, 0)
    ):
        return False
    message = str(execution.failure_message or "")
    return bool(_NPM_ETARGET_CODE.search(message) and _NPM_NO_MATCHING_VERSION.search(message))


def is_npm_eresolve_failure(execution) -> bool:
    """Recognize persisted npm ERESOLVE dependency-resolution evidence."""
    if (
        execution is None
        or execution.command_id != "npm-lockfile-generate"
        or execution.status != "failed"
        or execution.exit_code in (None, 0)
    ):
        return False
    return bool(_NPM_ERESOLVE.search(str(execution.failure_message or "")))


def _file_checksum(path: Path) -> str:
    return (
        "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_file() and not path.is_symlink()
        else "missing"
    )


def _is_governed_volatile_relative(relative: str) -> bool:
    """True when any path part is a governed volatile root (node_modules/** etc.).

    Mirrors the casefold-any-part semantics of the stage fingerprint profile
    (``workspace_fingerprint_v1``) so the lockfile mutation proof governs the
    exact same tree authority as the stage binding fingerprint.
    """
    return any(part.casefold() in STAGE_VOLATILE_NAMES for part in relative.split("/"))


def workspace_excluding_governed_volatile_fingerprint(workspace: Path) -> str:
    """Governed mutation-scope fingerprint for npm-lockfile-generate (v2).

    Scope: the root package-lock.json and every governed volatile root
    (node_modules/**, .angular/**, dist/**, ...) may change; every other file
    must be byte-identical across the command.  ``package.json`` stays inside
    the governed scope and is additionally pinned by its own checksum guard.
    """
    root = workspace.resolve(strict=True)
    entries = []
    for item in root.rglob("*"):
        relative = item.relative_to(root).as_posix()
        if relative == "package-lock.json":
            continue
        if _is_governed_volatile_relative(relative):
            continue
        if item.is_symlink():
            entries.append((relative, b"symlink:" + os.readlink(item).encode()))
        elif item.is_dir():
            entries.append((relative + "/", b"directory"))
        elif item.is_file():
            entries.append((relative, item.read_bytes()))
    return STAGE_FINGERPRINT_PROFILE.fingerprint_manifest(entries)


class LockfileGenerationRunner:
    def __init__(self, *, stage_service=None, now_provider=None) -> None:
        self._stage = stage_service or TransformerStageService()
        self._now = now_provider or (lambda: datetime.now(UTC))

    def advance(self, session, continuation, *, next_node: str) -> str:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "lockfile_generation-0",
            )
        )
        if step is None:
            raise LockfileGenerationError(
                "STAGE_PLAN_COMMAND_AUTHORITY_MISSING",
                "The immutable G06-approved stage plan lacks npm-lockfile-generate authority",
            )
        if step.status == "PASSED":
            if not self._verification_metadata(session, step.execution_id):
                raise LockfileGenerationError(
                    "LOCKFILE_GENERATION_EVIDENCE_MISSING",
                    "Lockfile-generation verification evidence is missing",
                )
            self._resume(continuation, next_node)
            return "passed"
        execution = session.get(CommandExecutionModel, step.execution_id) if step.execution_id else None
        if execution is None:
            return self._queue(session, continuation)
        if execution.status in {"pending", "queued", "running"}:
            self._stage._wait_for_command(session, continuation, execution.id)
            return "waiting"
        if execution.status != "succeeded" or execution.exit_code != 0:
            if is_npm_etarget_failure(execution):
                raise LockfileGenerationError(
                    LOCKFILE_GENERATION_ETARGET,
                    execution.failure_message or "npm reported an unavailable dependency version",
                )
            if is_npm_eresolve_failure(execution):
                raise LockfileGenerationError(
                    LOCKFILE_GENERATION_ERESOLVE,
                    execution.failure_message or "npm reported an unresolved dependency tree",
                )
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_COMMAND_FAILED",
                execution.failure_code or "npm-lockfile-generate did not succeed",
            )
        if (execution.start_fingerprint or {}).get("fingerprint_scope") != LOCKFILE_GENERATION_FINGERPRINT_SCOPE:
            return self._queue_successor(session, continuation, execution)
        self._verify(session, continuation, step, execution)
        self._record_catalogue_evidence(session, continuation, execution)
        self._resume(continuation, next_node)
        return "passed"

    def _record_catalogue_evidence(self, session, continuation, execution) -> None:
        """Record F08 catalogue-compatibility evidence for the generated lockfile.

        Supplementary to the runner's prequalification gate: a catalogue verdict
        (including blockers) is frozen per stage with the execution's runtime
        binding.  Never fails the step — the evidence is a durable record.
        """
        try:
            from app.repositories.models import LockfileGenerationEvidenceModel, MigrationStageModel, StageWorkspaceBindingModel
            from app.services.lockfile_compatibility_service import LockfileCompatibilityService

            stage = session.get(MigrationStageModel, continuation.current_stage_id)
            if stage is None or not stage.source_version_family or not stage.target_version_family:
                return
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == continuation.run_id,
                    StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if binding is None:
                return
            workspace = Path(binding.workspace_path)
            if not workspace.is_dir():
                return
            service = LockfileCompatibilityService()
            verdict = service.validate_stage_lockfile(workspace, stage.source_version_family, stage.target_version_family)
            dependency_set = service.inspect_lockfile(workspace)
            evidence_id = "lke-" + hashlib.sha256(
                f"{continuation.run_id}:{stage.id}:{dependency_set.checksum}".encode()
            ).hexdigest()[:24]
            existing = session.get(LockfileGenerationEvidenceModel, evidence_id)
            if existing is not None:
                return
            session.add(
                LockfileGenerationEvidenceModel(
                    id=evidence_id,
                    run_id=continuation.run_id,
                    stage_id=stage.id,
                    execution_id=execution.id,
                    lockfile_checksum=dependency_set.checksum,
                    lockfile_version=dependency_set.lockfile_version,
                    source_family=verdict.source_family,
                    target_family=verdict.target_family,
                    node_version=None,
                    npm_version=None,
                    node_sha256=execution.runtime_checksum,
                    npm_sha256=None,
                    validation_status=verdict.status,
                    blockers=list(verdict.blockers),
                    findings=[finding.model_dump(mode="json") for finding in verdict.findings],
                    deterministic=True,
                    created_at=execution.finished_at or self._now(),
                )
            )
        except Exception:
            return

    def _queue(self, session, continuation, *, generation: int = 1) -> str:
        if generation not in {1, 2}:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_FINGERPRINT_INVALID",
                "Only one v1 -> v2 successor generation is permitted",
            )
        run, attempt, binding, workspace = self._authority(session, continuation)
        if (workspace / "npm-shrinkwrap.json").exists():
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_SHRINKWRAP_PRESENT",
                "Root npm-shrinkwrap.json forbids package-lock generation",
            )
        if generation == 1:
            if STAGE_FINGERPRINT_PROFILE.fingerprint(workspace) != binding.workspace_fingerprint:
                raise LockfileGenerationError(
                    "LOCKFILE_GENERATION_WORKSPACE_STALE",
                    "The post-apply workspace no longer matches its active binding",
                )
        else:
            self._require_successor_workspace(session, continuation, workspace)
        if binding.fingerprint_profile_id != STAGE_FINGERPRINT_PROFILE.profile_id:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_WORKSPACE_STALE",
                "The post-apply workspace binding lacks current fingerprint authority",
            )
        start = {
            "fingerprint_scope": LOCKFILE_GENERATION_FINGERPRINT_SCOPE,
            "post_apply_pre_command_package_json_sha256": _file_checksum(workspace / "package.json"),
            "post_apply_pre_command_package_lock_sha256": _file_checksum(workspace / "package-lock.json"),
            "post_apply_pre_command_governed_workspace_fingerprint": workspace_excluding_governed_volatile_fingerprint(workspace),
            "post_apply_pre_command_binding_fingerprint": binding.workspace_fingerprint,
        }
        if start["post_apply_pre_command_package_json_sha256"] == "missing":
            raise LockfileGenerationError("PACKAGE_JSON_MISSING", "Approved package.json is missing")
        try:
            result = self._stage.queue_lockfile_generation(
                session, continuation, attempt_key=self._attempt_key(attempt, generation)
            )
        except TransformerStageError as error:
            code = (
                "STAGE_PLAN_COMMAND_AUTHORITY_MISSING"
                if error.code == "STAGE_COMMAND_NOT_FOUND"
                else error.code
            )
            raise LockfileGenerationError(code, error.message) from error
        execution = session.get(CommandExecutionModel, result.execution_id)
        if execution is None:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_QUEUE_FAILED", "Queued command evidence is missing"
            )
        execution.start_fingerprint = start
        return "queued"

    @staticmethod
    def _attempt_key(attempt, generation: int) -> str:
        if generation == 1:
            return attempt.id
        return f"{attempt.id}{LOCKFILE_GENERATION_ATTEMPT_2_MARKER}"

    def _queue_successor(self, session, continuation, stale_execution) -> str:
        """Queue the one durable V1 -> V2 successor for a terminal stale-baseline execution.

        The stale (pre-scope) execution is never verified against v2 semantics
        and is never reused as the fresh command: a new execution with a
        deterministic attempt-2 idempotency generation re-runs
        npm-lockfile-generate and captures a fresh v2 pre-command baseline.
        """
        if LOCKFILE_GENERATION_ATTEMPT_2_MARKER in (stale_execution.idempotency_key or ""):
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_FINGERPRINT_INVALID",
                "A successor execution still carries a stale fingerprint baseline",
            )
        return self._queue(session, continuation, generation=2)

    def _require_successor_workspace(self, session, continuation, workspace) -> None:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "lockfile_generation-0",
            )
        )
        stale_execution = session.get(CommandExecutionModel, step.execution_id) if step is not None else None
        if stale_execution is None or not (stale_execution.start_fingerprint or {}):
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_FINGERPRINT_INVALID",
                "No durable predecessor baseline authorizes a v2 successor",
            )
        start = stale_execution.start_fingerprint
        expected_package = start.get("post_apply_pre_command_package_json_sha256")
        if not expected_package or _file_checksum(workspace / "package.json") != expected_package:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_WORKSPACE_STALE",
                "The successor workspace no longer matches the approved post-apply package.json",
            )
        governed = start.get("post_apply_pre_command_governed_workspace_fingerprint")
        if governed is not None and workspace_excluding_governed_volatile_fingerprint(workspace) != governed:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_WORKSPACE_STALE",
                "The successor workspace drifted outside the governed lockfile mutation scope",
            )

    def _authority(self, session, continuation):
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
        if run is None or attempt is None or binding is None or not run.artifact_root:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_AUTHORITY_MISSING",
                "Lockfile-generation authority is incomplete",
            )
        if attempt.status not in {"applied", "applied_verified"} or not self._has_approved_dependency_change(
            session, run, attempt, continuation.current_stage_id
        ):
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_NOT_APPROVED",
                "No applied G10-approved dependency change or addition authorizes lockfile generation",
            )
        try:
            workspace = Path(binding.workspace_path).resolve(strict=True)
            workspace.relative_to(Path(run.run_root).resolve(strict=True))
        except (OSError, ValueError) as error:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_WORKSPACE_INVALID",
                "The bound stage workspace is unavailable or outside the run root",
            ) from error
        return run, attempt, binding, workspace

    @staticmethod
    def _has_approved_dependency_change(session, run, attempt, stage_id: str) -> bool:
        if not attempt.proposal_artifact_id or not attempt.proposal_checksum:
            return False
        metadata = session.get(ArtifactMetadataModel, "metadata-" + attempt.proposal_artifact_id)
        if metadata is None or metadata.checksum != attempt.proposal_checksum:
            return False
        try:
            stored = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent,
                fixed_run_root=Path(run.artifact_root),
            ).read_artifact(run.id, metadata.relative_path)
            proposal = RepairProposal.model_validate(json.loads(stored.content))
        except (OSError, ValueError):
            return False
        return (
            stored.ref.checksum == attempt.proposal_checksum
            and stored.envelope is not None
            and stored.envelope.stage_id == stage_id
            and stored.envelope.attempt_id == attempt.id
            and any(
                item.operation in {"dependency_change", "dependency_add"}
                for item in proposal.operations
            )
        )

    def _verify(self, session, continuation, step, execution) -> None:
        run, _attempt, binding, workspace = self._authority(session, continuation)
        start = execution.start_fingerprint or {}
        if start.get("fingerprint_scope") != LOCKFILE_GENERATION_FINGERPRINT_SCOPE:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_FINGERPRINT_INVALID",
                "A v1-baseline execution cannot be verified under v2 fingerprint semantics",
            )
        expected_package = start.get("post_apply_pre_command_package_json_sha256")
        expected_workspace = start.get("post_apply_pre_command_governed_workspace_fingerprint")
        expected_binding = start.get("post_apply_pre_command_binding_fingerprint")
        if expected_package is None or expected_workspace is None:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_EVIDENCE_INCOMPLETE",
                "The v2 pre-command fingerprint baseline is incomplete",
            )
        package_checksum = _file_checksum(workspace / "package.json")
        lock_checksum = _file_checksum(workspace / "package-lock.json")
        workspace_without_lock = workspace_excluding_governed_volatile_fingerprint(workspace)
        if package_checksum != expected_package:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_PACKAGE_JSON_MUTATED",
                "npm-lockfile-generate modified approved package.json",
            )
        if workspace_without_lock != expected_workspace:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_UNEXPECTED_MUTATION",
                "npm-lockfile-generate changed files outside root package-lock.json",
            )
        if lock_checksum == "missing":
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_LOCKFILE_MISSING",
                "npm-lockfile-generate did not produce package-lock.json",
            )
        required_artifacts = (
            execution.stdout_artifact_id,
            execution.stderr_artifact_id,
            execution.command_log_artifact_id,
            execution.result_artifact_id,
            execution.manifest_artifact_id,
        )
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        planned_commands = (
            ((stage_plan.stage_plan or {}).get("commands") or {}).get("lockfile_generation")
            if stage_plan is not None
            else None
        )
        planned = planned_commands[0] if planned_commands and len(planned_commands) == 1 else {}
        if (
            execution.runtime_checksum != planned.get("runtime_profile_checksum")
            or execution.command_id != "npm-lockfile-generate"
            or execution.executable != planned.get("executable")
            or list(execution.arguments or []) != list(planned.get("arguments") or [])
            or execution.working_directory_alias != binding.alias
            or not execution.correlation_id
            or any(not artifact_id for artifact_id in required_artifacts)
            or any(
                session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id)) is None
                for artifact_id in required_artifacts
            )
        ):
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_EVIDENCE_INCOMPLETE",
                "Command execution artifacts or runtime correlation are incomplete",
            )
        try:
            package = PackageMetadataInspector().inspect(workspace)
            lock = LockfilePrequalificationService().inspect(workspace, package)
        except BaselineQualificationError as error:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_PACKAGE_INVALID", str(error)
            ) from error
        if lock.status != "valid":
            code = (
                "LOCKFILE_GENERATION_LOCKFILE_INVALID"
                if "NPM_LOCKFILE_INVALID" in lock.blockers
                else "LOCKFILE_GENERATION_LOCKFILE_UNSYNCHRONIZED"
            )
            raise LockfileGenerationError(code, ", ".join(lock.blockers))
        post_binding = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
        end = {
            "post_command_package_json_sha256": package_checksum,
            "post_command_package_lock_sha256": lock_checksum,
            "post_command_governed_workspace_fingerprint": workspace_without_lock,
            "post_command_binding_fingerprint": post_binding,
        }
        payload = {
            "schema_version": "lockfile-generation-verification.v2",
            "execution_id": execution.id,
            "stage_step_id": step.id,
            "correlation_id": execution.correlation_id,
            "command": {
                "executable": execution.executable,
                "arguments": list(execution.arguments or []),
                "working_directory_alias": execution.working_directory_alias,
                "runtime_profile_id": execution.runtime_profile_id,
                "runtime_checksum": execution.runtime_checksum,
                "exit_code": execution.exit_code,
            },
            "pre_command": start,
            "post_command": end,
            "lockfile_status": lock.status,
        }
        stored = self._write_or_recover_verification(run, continuation, execution, payload)
        metadata_id = "metadata-" + stored.ref.artifact_id
        metadata = session.get(ArtifactMetadataModel, metadata_id)
        cas = session.execute(
            update(StageWorkspaceBindingModel)
            .where(
                StageWorkspaceBindingModel.id == binding.id,
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
                StageWorkspaceBindingModel.workspace_path == binding.workspace_path,
                StageWorkspaceBindingModel.workspace_fingerprint == expected_binding,
                StageWorkspaceBindingModel.fingerprint_profile_id
                == STAGE_FINGERPRINT_PROFILE.profile_id,
            )
            .values(
                workspace_fingerprint=post_binding,
                last_verified_fingerprint=post_binding,
                last_verified_at=self._now(),
            )
        )
        if cas.rowcount != 1:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_BINDING_STALE",
                "The active workspace binding changed before lockfile verification committed",
            )
        if metadata is None:
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
                    execution_id=execution.id,
                    owner_reference=f"{execution.id}:lockfile-generation-verification",
                    mime_type=stored.envelope.content_type,
                    size_bytes=len(stored.content.encode("utf-8")),
                    finalized_at=stored.ref.created_at,
                    immutable=True,
                    redacted=False,
                    truncated=False,
                    correlation_id=execution.correlation_id,
                    safe_metadata={
                        "stage_step_id": step.id,
                        "binding_id": binding.id,
                        "pre_binding_fingerprint": expected_binding,
                        "post_binding_fingerprint": post_binding,
                    },
                )
            )
        artifact_id = stored.ref.artifact_id
        execution.end_fingerprint = end
        execution.artifact_ids = list(dict.fromkeys([*(execution.artifact_ids or []), artifact_id]))
        step.artifact_ids = list(dict.fromkeys([*(step.artifact_ids or []), artifact_id]))
        step.output_checksum = stored.ref.checksum
        step.workspace_fingerprint = post_binding
        step.status = "PASSED"
        step.completed_at = self._now()
        step.updated_at = self._now()

    @staticmethod
    def _verification_metadata(session, execution_id: str | None):
        if not execution_id:
            return None
        return session.scalar(
            select(ArtifactMetadataModel).where(
                ArtifactMetadataModel.execution_id == execution_id,
                ArtifactMetadataModel.owner_reference
                == f"{execution_id}:lockfile-generation-verification",
            )
        )

    def _write_or_recover_verification(self, run, continuation, execution, payload):
        content = json.dumps(payload, sort_keys=True, indent=2)
        checksum = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        store = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent,
            fixed_run_root=Path(run.artifact_root),
        )
        for ref in store.list_artifacts(run.id):
            if (
                ref.relative_path.startswith(
                    f"04_workflow_state/command_executions/{execution.id}.lockfile-verification"
                )
                and ref.checksum == checksum
            ):
                stored = store.read_artifact(run.id, ref.relative_path)
                if stored.envelope and stored.envelope.input_hashes.get("execution") == execution.id:
                    return stored
        return store.write_text_artifact(
            run.id,
            f"04_workflow_state/command_executions/{execution.id}.lockfile-verification.json",
            content,
            ArtifactType.JSON,
            stage_id=continuation.current_stage_id,
            created_by="lockfile-generation-runner",
            created_at=self._now(),
            input_hashes={"execution": execution.id},
            policy_version="lockfile-generation-v1",
        )

    def _resume(self, continuation, next_node: str) -> None:
        continuation.status = "queued"
        continuation.current_node = next_node
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.waiting_execution_id = None
        continuation.state_version += 1
        continuation.updated_at = self._now()
