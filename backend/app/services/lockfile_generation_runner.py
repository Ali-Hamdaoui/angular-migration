"""Post-G10 governed npm lockfile generation and verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from app.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
)
from app.domain.baseline import (
    BaselineQualificationError,
    LockfilePrequalificationService,
    PackageMetadataInspector,
)
from app.domain.contracts import ArtifactType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationStageModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageRecoveryOperationModel,
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
LOCKFILE_RECONCILIATION_MARKER = ":reconcile-stale-lock"
LOCKFILE_GENERATION_ETARGET = "LOCKFILE_GENERATION_ETARGET"
LOCKFILE_GENERATION_ERESOLVE = "LOCKFILE_GENERATION_ERESOLVE"

#: Frozen contract for P4 V2.2 dependency normalization — preserve-first materialization.
DEPENDENCY_NORMALIZATION_REPAIR_KIND = "dependency_manifest_normalization"
DEPENDENCY_NORMALIZATION_SCHEMA_VERSION = "dependency-normalization-v1"
DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED = "DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED"

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

# lock-specific malformed/unsupported evidence — NOT ERESOLVE/ETARGET peer conflict.
_NPM_LOCK_MALFORMED = re.compile(
    r"(?im)EBADLOCK|EINVALID|lockfile.*(?:corrupt|invalid|unsupported)|"
    r"unsupported.*lockfile|lockfileVersion.*unsupported|"
    r"must be.*lockfileVersion|ETARGET.*lockfile"
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


def _is_normalization_op(op: object) -> bool:
    if not isinstance(op, dict):
        return False
    return (
        str(op.get("repair_kind") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
        or str(op.get("operation") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
        or str(op.get("schema_version") or "") == DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
    )


def _proposal_is_normalization(proposal: object) -> bool:
    if not isinstance(proposal, dict):
        return False
    ops = proposal.get("operations")
    if not isinstance(ops, list):
        return False
    return any(_is_normalization_op(op) for op in ops)


def _is_lock_malformed_evidence(workspace: Path) -> bool:
    lock = workspace / "package-lock.json"
    if not lock.is_file() or lock.is_symlink():
        return True
    try:
        data = json.loads(lock.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return True
    if not isinstance(data, dict):
        return True
    ver = data.get("lockfileVersion")
    if not isinstance(ver, int) or ver < 1 or ver > 3:
        return True
    # structural: packages vs dependencies missing entirely
    if not isinstance(data.get("packages"), dict) and not isinstance(data.get("dependencies"), dict):
        # empty lockfile without packages is considered malformed for v3 verification
        # treat as unusable only when lockfileVersion claims v3
        if ver >= 3:
            return True
    return False


def _failure_message_indicates_lock_corrupt(message: str) -> bool:
    return bool(_NPM_LOCK_MALFORMED.search(message or ""))


def validate_generated_lockfile(workspace: Path) -> str:
    """Validate the generic npm lockfile against the current manifest."""
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
    return lock.status


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

    def _detect_normalization(self, session, continuation) -> tuple[bool, object | None]:
        """True when the active applied repair is dependency_manifest_normalization.

        Reads the immutable repair proposal artifact bound to the active attempt
        (same as _authority's check) and inspects repair_kind / operation /
        schema_version without touching filesystem outside the store.
        """
        try:
            run = session.get(MigrationRunModel, continuation.run_id)
            attempt = session.scalar(
                select(RepairAttemptModel)
                .where(
                    RepairAttemptModel.run_id == continuation.run_id,
                    RepairAttemptModel.stage_id == continuation.current_stage_id,
                    RepairAttemptModel.status.in_(("applied", "applied_verified")),
                )
                .order_by(RepairAttemptModel.attempt_number.desc())
            )
            if run is None or attempt is None or not run.artifact_root:
                return False, None
            if not attempt.proposal_artifact_id or not attempt.proposal_checksum:
                return False, None
            metadata = session.get(ArtifactMetadataModel, "metadata-" + attempt.proposal_artifact_id)
            if metadata is None or metadata.checksum != attempt.proposal_checksum:
                return False, None
            stored = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
            ).read_artifact(run.id, metadata.relative_path)
            if stored.ref.checksum != attempt.proposal_checksum:
                return False, None
            proposal = json.loads(stored.content)
            if _proposal_is_normalization(proposal):
                return True, attempt
            # also accept the Pydantic view for legacy stored shape
            try:
                parsed = RepairProposal.model_validate(proposal)
                for item in parsed.operations:
                    if item.operation == DEPENDENCY_NORMALIZATION_REPAIR_KIND or (item.repair_kind or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND:
                        return True, attempt
            except Exception:
                pass
            return False, attempt
        except Exception:
            return False, None

    def _normalization_fresh_fallback_qualified(self, workspace: Path, execution) -> bool:
        """Qualified fresh-lock fallback: only when lock itself proves malformed/unsupported/corrupt.

        Never on mere ERESOLVE/ETARGET peer-conflict evidence. Reuses the lock-malformed
        predicate and lock-specific corrupt pattern; callers reuse the existing governed
        stale-lock preparation primitive rather than building a second recovery system.
        """
        if _is_lock_malformed_evidence(workspace):
            return True
        if _failure_message_indicates_lock_corrupt(str(execution.failure_message or "")):
            return True
        return False

    def _record_normalization_failure_evidence(self, session, continuation, execution, workspace, attempt) -> None:
        """Persist immutable normalized evidence for a DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED.

        The evidence freezes package.json / package-lock checksums, plan number, generation,
        and the npm failure message so P6 can enforce plan1->new constraint->plan2->BLOCK.
        """
        try:
            run = session.get(MigrationRunModel, continuation.run_id)
            if run is None or not run.artifact_root:
                return
            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
            )
            start = execution.start_fingerprint or {}
            plan_number = getattr(attempt, "attempt_number", None) if attempt is not None else None
            generation = start.get("normalization_generation") or start.get("reconciliation_generation") or 1
            payload = {
                "schema_version": "dependency-normalization-failure-v1",
                "repair_kind": DEPENDENCY_NORMALIZATION_REPAIR_KIND,
                "normalization_schema_version": DEPENDENCY_NORMALIZATION_SCHEMA_VERSION,
                "plan_number": plan_number,
                "generation": generation,
                "attempt_id": getattr(attempt, "id", None),
                "execution_id": execution.id,
                "stage_id": continuation.current_stage_id,
                "run_id": continuation.run_id,
                "package_json_sha256": _file_checksum(workspace / "package.json"),
                "package_lock_sha256": _file_checksum(workspace / "package-lock.json"),
                "pre_command_package_json_sha256": start.get("post_apply_pre_command_package_json_sha256"),
                "pre_command_package_lock_sha256": start.get("post_apply_pre_command_package_lock_sha256"),
                "pre_command_governed_workspace_fingerprint": start.get("post_apply_pre_command_governed_workspace_fingerprint"),
                "failure_code": execution.failure_code,
                "failure_message": execution.failure_message,
                "exit_code": execution.exit_code,
                "command_id": execution.command_id,
                "arguments": list(execution.arguments or []),
                "preserve_first": start.get("preserve_first") is True,
                "package_lock_only": start.get("package_lock_only") is True,
                "immutable": True,
            }
            content = json.dumps(payload, sort_keys=True, indent=2)
            checksum = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
            relative = f"05_repairs/attempt-{attempt.id}/dependency-normalization-failure.{execution.id}.{checksum[7:15]}.json" if attempt and getattr(attempt, "id", None) else f"04_workflow_state/command_executions/{execution.id}.dependency-normalization-failure.json"
            stored = store.write_text_artifact(
                run.id,
                relative,
                content,
                ArtifactType.JSON,
                stage_id=continuation.current_stage_id,
                attempt_id=getattr(attempt, "id", None),
                created_by="lockfile-generation-runner",
                created_at=self._now(),
                input_hashes={
                    "execution": execution.id,
                    "package_json": payload["package_json_sha256"],
                    "package_lock": payload["package_lock_sha256"],
                    "failure_message": hashlib.sha256(str(execution.failure_message or "").encode()).hexdigest()[:16],
                },
                policy_version="dependency-normalization-failure-v1",
            )
            meta_id = "metadata-" + stored.ref.artifact_id
            if session.get(ArtifactMetadataModel, meta_id) is None:
                session.add(
                    ArtifactMetadataModel(
                        id=meta_id,
                        run_id=run.id,
                        stage_id=continuation.current_stage_id,
                        artifact_type=stored.ref.artifact_type.value,
                        relative_path=stored.ref.relative_path,
                        checksum=stored.ref.checksum,
                        schema_version=stored.envelope.schema_version,
                        created_at=stored.ref.created_at,
                        finalized_at=stored.ref.created_at,
                        immutable=True,
                        execution_id=execution.id,
                        owner_reference=f"{execution.id}:dependency-normalization-failure",
                        correlation_id=execution.correlation_id,
                        safe_metadata={
                            "repair_kind": DEPENDENCY_NORMALIZATION_REPAIR_KIND,
                            "schema_version": DEPENDENCY_NORMALIZATION_SCHEMA_VERSION,
                            "plan_number": plan_number,
                            "generation": generation,
                            "immutable_normalized_evidence": True,
                        },
                    )
                )
                session.flush()
        except Exception:
            return

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
            # P4 V2.2 preserve-first normalization path — ERESOLVE/ETARGET become
            # DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED with immutable evidence.
            # Historical reconciliation routes are preserved for non-normalization.
            is_norm, norm_attempt = self._detect_normalization(session, continuation)
            if is_norm and (is_npm_etarget_failure(execution) or is_npm_eresolve_failure(execution)):
                workspace_for_norm: Path | None = None
                binding_for_norm = session.scalar(
                    select(StageWorkspaceBindingModel).where(
                        StageWorkspaceBindingModel.run_id == continuation.run_id,
                        StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                        StageWorkspaceBindingModel.active.is_(True),
                    )
                )
                if binding_for_norm is not None:
                    try:
                        workspace_for_norm = Path(binding_for_norm.workspace_path).resolve(strict=True)
                    except (OSError, ValueError):
                        workspace_for_norm = None
                # package.json mutation guard — do not hide a mutation behind a resolution failure
                if workspace_for_norm is not None:
                    start_guard = execution.start_fingerprint or {}
                    expected_pkg = start_guard.get("post_apply_pre_command_package_json_sha256")
                    if expected_pkg is not None and _file_checksum(workspace_for_norm / "package.json") != expected_pkg:
                        raise LockfileGenerationError(
                            "LOCKFILE_GENERATION_PACKAGE_JSON_MUTATED",
                            "npm-lockfile-generate modified approved package.json",
                        )
                    # qualified fresh-lock fallback ONLY when lock itself is malformed/unsupported/corrupt
                    if self._normalization_fresh_fallback_qualified(workspace_for_norm, execution):
                        try:
                            return self._queue_stale_lock_reconciliation(session, continuation, execution)
                        except LockfileGenerationError as error:
                            if error.code not in {
                                "LOCKFILE_RECONCILIATION_WORKSPACE_STALE",
                                "LOCKFILE_RECONCILIATION_EVIDENCE_MISSING",
                                "LOCKFILE_RECONCILIATION_EVIDENCE_INVALID",
                            }:
                                raise
                            pass
                    self._record_normalization_failure_evidence(session, continuation, execution, workspace_for_norm, norm_attempt)
                raise LockfileGenerationError(
                    DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED,
                    execution.failure_message or "npm reported an unresolved dependency tree for normalized manifest",
                )
            if is_npm_etarget_failure(execution):
                raise LockfileGenerationError(
                    LOCKFILE_GENERATION_ETARGET,
                    execution.failure_message or "npm reported an unavailable dependency version",
                )
            if is_npm_eresolve_failure(execution):
                start = execution.start_fingerprint or {}
                if start.get("current_state_reconciliation") is True:
                    return self._queue_stale_lock_reconciliation(
                        session, continuation, execution
                    )
                if start.get("reconciliation_generation") is True:
                    raise LockfileGenerationError(
                        LOCKFILE_GENERATION_ERESOLVE,
                        execution.failure_message
                        or "npm reported an unresolved dependency tree",
                    )
                if self._current_state_reconciliation_allowed(
                    session, continuation, execution
                ):
                    return self._queue_current_state_reconciliation(
                        session, continuation, execution
                    )
                if self._stale_lock_reconciliation_allowed(session, continuation, execution):
                    try:
                        return self._queue_stale_lock_reconciliation(
                            session, continuation, execution
                        )
                    except LockfileGenerationError as error:
                        if error.code not in {
                            "LOCKFILE_RECONCILIATION_WORKSPACE_STALE",
                            "LOCKFILE_RECONCILIATION_EVIDENCE_MISSING",
                            "LOCKFILE_RECONCILIATION_EVIDENCE_INVALID",
                        }:
                            raise
                        return self._queue_current_state_reconciliation(
                            session, continuation, execution
                        )
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
        resume_node = (execution.start_fingerprint or {}).get(
            "post_reconciliation_next_node", next_node
        )
        self._resume(continuation, resume_node)
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

    def _queue(
        self,
        session,
        continuation,
        *,
        generation: int = 1,
        reconciliation_key: str | None = None,
        current_state: bool = False,
        next_node: str | None = None,
    ) -> str:
        if generation not in {1, 2, 3}:
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
        elif current_state and generation == 3:
            if STAGE_FINGERPRINT_PROFILE.fingerprint(workspace) != binding.workspace_fingerprint:
                raise LockfileGenerationError(
                    "LOCKFILE_GENERATION_WORKSPACE_STALE",
                    "The current reconciliation workspace no longer matches its active binding",
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
            "reconciliation_generation": generation == 3,
            "current_state_reconciliation": current_state,
            "post_apply_pre_command_package_json_sha256": _file_checksum(workspace / "package.json"),
            "post_apply_pre_command_package_lock_sha256": _file_checksum(workspace / "package-lock.json"),
            "post_apply_pre_command_governed_workspace_fingerprint": workspace_excluding_governed_volatile_fingerprint(workspace),
            "post_apply_pre_command_binding_fingerprint": binding.workspace_fingerprint,
        }
        # P4 V2.2 preserve-first / package-lock-only visibility for P6 enforcement
        is_norm_start, _norm_att_start = self._detect_normalization(session, continuation)
        if is_norm_start:
            start["normalization_repair_kind"] = DEPENDENCY_NORMALIZATION_REPAIR_KIND
            start["normalization_schema_version"] = DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
            start["normalization_plan_number"] = getattr(attempt, "attempt_number", None)
            start["normalization_generation"] = generation
            start["dependency_normalization_generation"] = generation
            start["preserve_first"] = True
            start["package_lock_only"] = True
        else:
            start["preserve_first"] = generation == 1
            start["package_lock_only"] = True
        if start["post_apply_pre_command_package_json_sha256"] == "missing":
            raise LockfileGenerationError("PACKAGE_JSON_MISSING", "Approved package.json is missing")
        try:
            result = self._stage.queue_lockfile_generation(
                session,
                continuation,
                attempt_key=self._attempt_key(attempt, generation, reconciliation_key),
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
        if next_node is not None:
            execution.start_fingerprint["post_reconciliation_next_node"] = next_node
        return "queued"

    def _current_state_reconciliation_allowed(self, session, continuation, execution) -> bool:
        if (execution.start_fingerprint or {}).get("current_state_reconciliation") is True:
            return False
        run, _attempt, _binding, workspace = self._authority(session, continuation)
        stage = session.get(MigrationStageModel, continuation.current_stage_id)
        if stage is None:
            return False
        from app.services.dependency_repair_preflight_service import DependencyRepairPreflightService

        diagnosis = DependencyRepairPreflightService().classify_current_state(
            workspace=workspace,
            source_family=stage.source_version_family,
            target_family=stage.target_version_family,
        )
        return diagnosis.get("classification") == "TARGET_MANIFEST_AHEAD"

    def _queue_current_state_reconciliation(self, session, continuation, failed_execution) -> str:
        """Queue a fresh lockfile command from the current target manifest.

        The historical ERESOLVE remains the causal diagnostic, but its old
        package/lockfile baseline cannot authorize mutation after the manifest
        has advanced.  The current governed binding becomes the new command
        baseline and the idempotency key includes both generations.
        """
        run, _attempt, _binding, workspace = self._authority(session, continuation)
        stage = session.get(MigrationStageModel, continuation.current_stage_id)
        if stage is None:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_AUTHORITY_MISSING",
                "The stage authority is missing for current-state reconciliation",
            )
        from app.services.dependency_repair_preflight_service import DependencyRepairPreflightService

        diagnosis = DependencyRepairPreflightService().classify_current_state(
            workspace=workspace,
            source_family=stage.source_version_family,
            target_family=stage.target_version_family,
        )
        if diagnosis.get("classification") != "TARGET_MANIFEST_AHEAD":
            raise LockfileGenerationError(
                "DEPENDENCY_STATE_RECONCILIATION_NOT_APPLICABLE",
                f"Current dependency state is {diagnosis.get('classification')}",
            )
        result = session.get(
            ArtifactMetadataModel,
            "metadata-" + str(failed_execution.result_artifact_id),
        )
        if result is None or not result.immutable or result.execution_id != failed_execution.id:
            raise LockfileGenerationError(
                "LOCKFILE_RECONCILIATION_EVIDENCE_MISSING",
                "The historical lockfile failure result is unavailable",
            )
        package_checksum = _file_checksum(workspace / "package.json")
        lock_checksum = _file_checksum(workspace / "package-lock.json")
        request = {
            "run_id": run.id,
            "stage_id": continuation.current_stage_id,
            "failed_execution_id": failed_execution.id,
            "failed_result_checksum": result.checksum,
            "package_json_checksum": package_checksum,
            "package_lock_checksum": lock_checksum,
            "classification": diagnosis["classification"],
        }
        reconciliation_checksum = hashlib.sha256(
            json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self._queue(
            session,
            continuation,
            generation=3,
            reconciliation_key=f"current:{reconciliation_checksum}",
            current_state=True,
            next_node="repair_revalidate",
        )
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "lockfile_generation-0",
            )
        )
        queued = session.get(CommandExecutionModel, step.execution_id) if step else None
        if queued is None:
            raise LockfileGenerationError(
                "LOCKFILE_GENERATION_QUEUE_FAILED",
                "Current-state reconciliation command evidence is missing",
            )
        return "queued"

    @staticmethod
    def _attempt_key(attempt, generation: int, reconciliation_key: str | None = None) -> str:
        if generation == 1:
            return attempt.id
        marker = (
            LOCKFILE_GENERATION_ATTEMPT_2_MARKER
            if generation == 2
            else f"{LOCKFILE_RECONCILIATION_MARKER}:{reconciliation_key}"
        )
        return f"{attempt.id}{marker}"

    def _stale_lock_reconciliation_allowed(self, session, continuation, execution) -> bool:
        if (
            LOCKFILE_RECONCILIATION_MARKER in str(execution.idempotency_key or "")
            or (execution.start_fingerprint or {}).get("reconciliation_generation")
        ):
            return False
        run, _attempt, _binding, workspace = self._authority(session, continuation)
        stage = session.get(MigrationStageModel, continuation.current_stage_id)
        if stage is None:
            return False
        from app.services.dependency_repair_preflight_service import DependencyRepairPreflightService

        diagnosis = DependencyRepairPreflightService().classify_current_state(
            workspace=workspace,
            source_family=stage.source_version_family,
            target_family=stage.target_version_family,
        )
        return diagnosis.get("classification") == "TARGET_MANIFEST_AHEAD"

    def _reusable_preparation(self, session, continuation, execution, package_checksum, governed):
        run, _attempt, _binding, workspace = self._authority(session, continuation)
        if (workspace / "package-lock.json").exists():
            return None
        for candidate in session.scalars(
            select(ArtifactMetadataModel)
            .where(
                ArtifactMetadataModel.run_id == run.id,
                ArtifactMetadataModel.stage_id == continuation.current_stage_id,
                ArtifactMetadataModel.owner_reference.like("%:stale-lock:%"),
                ArtifactMetadataModel.immutable.is_(True),
            )
            .order_by(ArtifactMetadataModel.created_at.desc())
        ):
            metadata = candidate.safe_metadata or {}
            failed = session.get(
                CommandExecutionModel, metadata.get("failed_execution_id")
            )
            if (
                metadata.get("package_json_checksum") != package_checksum
                or metadata.get("governed_workspace_fingerprint") != governed
                or failed is None
                or failed.run_id != run.id
                or failed.stage_id != continuation.current_stage_id
                or failed.command_id != "npm-lockfile-generate"
                or failed.status != "failed"
                or failed.exit_code in (None, 0)
            ):
                continue
            try:
                stored = LocalFilesystemArtifactStore(
                    Path(run.artifact_root).parent,
                    fixed_run_root=Path(run.artifact_root),
                ).read_artifact(run.id, candidate.relative_path)
            except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError):
                continue
            if stored.ref.checksum == candidate.checksum:
                return metadata
        return None

    def _queue_stale_lock_reconciliation(
        self,
        session,
        continuation,
        execution,
        *,
        recovery_id: str | None = None,
        recovery_owned: bool = False,
    ) -> str:
        run, attempt, binding, workspace = self._authority(session, continuation)
        lockfile = workspace / "package-lock.json"
        start = execution.start_fingerprint or {}
        result = session.get(
            ArtifactMetadataModel, "metadata-" + str(execution.result_artifact_id)
        )
        expected_lock = start.get("post_apply_pre_command_package_lock_sha256")
        expected_package = start.get("post_apply_pre_command_package_json_sha256")
        if result is None or not result.immutable or result.execution_id != execution.id:
            raise LockfileGenerationError(
                "LOCKFILE_RECONCILIATION_EVIDENCE_MISSING",
                "The causal lockfile result evidence is unavailable",
            )
        identity_payload = {
            "run_id": continuation.run_id,
            "stage_id": continuation.current_stage_id,
            "repair_attempt_id": attempt.id,
            "failed_execution_id": execution.id,
            "failed_execution_result_checksum": result.checksum,
            "stale_lockfile_checksum": expected_lock,
            "package_json_checksum": expected_package,
        }
        reconciliation_checksum = hashlib.sha256(
            json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        owner = (
            f"{recovery_id}:stale-lock:{reconciliation_checksum[:24]}"
            if recovery_id
            else f"{execution.id}:stale-lock:{reconciliation_checksum[:24]}"
        )
        preparation = session.scalar(
            select(ArtifactMetadataModel).where(
                ArtifactMetadataModel.run_id == continuation.run_id,
                ArtifactMetadataModel.stage_id == continuation.current_stage_id,
                ArtifactMetadataModel.owner_reference == owner,
                ArtifactMetadataModel.immutable.is_(True),
            )
        )
        if preparation is None and expected_lock == "missing":
            reusable = self._reusable_preparation(
                session,
                continuation,
                execution,
                expected_package,
                start.get("post_apply_pre_command_governed_workspace_fingerprint"),
            )
            if reusable is not None:
                return self._queue(
                    session,
                    continuation,
                    generation=3,
                    reconciliation_key=(
                        f"resume:{reusable['reconciliation_checksum']}:{execution.id}"
                    ),
                )
        if preparation is None:
            if (
                not lockfile.is_file()
                or lockfile.is_symlink()
                or _file_checksum(lockfile) != expected_lock
                or _file_checksum(workspace / "package.json") != expected_package
                or STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
                != binding.workspace_fingerprint
            ):
                raise LockfileGenerationError(
                    "LOCKFILE_RECONCILIATION_WORKSPACE_STALE",
                    "The stale lockfile preparation source changed",
                )
            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
            )
            stored = store.write_text_artifact(
                run.id,
                (
                    f"04_workflow_state/recovery/{recovery_id}/stale-package-lock."
                    f"{reconciliation_checksum}.json"
                    if recovery_id
                    else f"05_repairs/attempt-{attempt.id}/stale-package-lock.{reconciliation_checksum}.json"
                ),
                lockfile.read_text(encoding="utf-8"),
                ArtifactType.JSON,
                stage_id=continuation.current_stage_id,
                attempt_id=attempt.id,
                created_by="lockfile-generation-runner",
                created_at=self._now(),
                input_hashes={
                    "failed_execution": execution.id,
                    "result": result.checksum,
                    "lockfile": expected_lock,
                    "manifest": expected_package,
                },
                policy_version="dependency-state-reconciliation-v2",
            )
            session.add(
                ArtifactMetadataModel(
                    id="metadata-" + stored.ref.artifact_id,
                    run_id=run.id,
                    stage_id=continuation.current_stage_id,
                    artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path,
                    checksum=stored.ref.checksum,
                    created_at=stored.ref.created_at,
                    finalized_at=stored.ref.created_at,
                    immutable=True,
                    execution_id=execution.id,
                    owner_reference=owner,
                    safe_metadata={
                        **identity_payload,
                        "reconciliation_checksum": reconciliation_checksum,
                        "preparation_binding_fingerprint": binding.workspace_fingerprint,
                        "governed_workspace_fingerprint": start.get(
                            "post_apply_pre_command_governed_workspace_fingerprint"
                        ),
                    },
                )
            )
            if not recovery_owned:
                self._resume(continuation, "lockfile_generation")
            return "preparing"

        metadata = preparation.safe_metadata or {}
        if metadata.get("reconciliation_checksum") != reconciliation_checksum:
            raise LockfileGenerationError(
                "LOCKFILE_RECONCILIATION_EVIDENCE_INVALID",
                "Stale-lock preparation identity does not match causal evidence",
            )
        pre_binding = metadata.get("preparation_binding_fingerprint")
        if lockfile.exists():
            if lockfile.is_symlink() or _file_checksum(lockfile) != expected_lock:
                raise LockfileGenerationError(
                    "LOCKFILE_RECONCILIATION_WORKSPACE_STALE",
                    "The stale lockfile changed after preparation",
                )
            lockfile.unlink()
        if (
            _file_checksum(workspace / "package.json") != expected_package
            or workspace_excluding_governed_volatile_fingerprint(workspace)
            != metadata.get("governed_workspace_fingerprint")
        ):
            raise LockfileGenerationError(
                "LOCKFILE_RECONCILIATION_WORKSPACE_STALE",
                "Workspace changed outside the governed stale-lock scope",
            )
        prepared_fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
        if binding.workspace_fingerprint == pre_binding:
            cas = session.execute(
                update(StageWorkspaceBindingModel)
                .where(
                    StageWorkspaceBindingModel.id == binding.id,
                    StageWorkspaceBindingModel.workspace_fingerprint == pre_binding,
                    StageWorkspaceBindingModel.active.is_(True),
                )
                .values(
                    workspace_fingerprint=prepared_fingerprint,
                    last_verified_fingerprint=prepared_fingerprint,
                    last_verified_at=self._now(),
                )
            )
            if cas.rowcount != 1:
                raise LockfileGenerationError(
                    "LOCKFILE_RECONCILIATION_BINDING_STALE",
                    "Workspace authority changed during stale-lock preparation",
                )
            binding.workspace_fingerprint = prepared_fingerprint
        elif binding.workspace_fingerprint != prepared_fingerprint:
            raise LockfileGenerationError(
                "LOCKFILE_RECONCILIATION_BINDING_STALE",
                "Prepared workspace does not match durable binding authority",
            )
        queue_reconciliation_key = (
            "recovery-"
            + hashlib.sha256(
                f"{recovery_id}:{reconciliation_checksum}".encode()
            ).hexdigest()[:48]
            if recovery_id
            else reconciliation_checksum
        )
        return self._queue(
            session,
            continuation,
            generation=3,
            reconciliation_key=queue_reconciliation_key,
        )

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
        recovery = session.scalar(
            select(StageRecoveryOperationModel)
            .where(
                StageRecoveryOperationModel.run_id == continuation.run_id,
                StageRecoveryOperationModel.stage_id == continuation.current_stage_id,
                StageRecoveryOperationModel.status.not_in(("COMPLETED", "FAILED")),
            )
            .order_by(StageRecoveryOperationModel.created_at.desc())
        )
        attempt = (
            session.get(RepairAttemptModel, recovery.repair_attempt_id)
            if recovery is not None and recovery.repair_attempt_id
            else session.scalar(
                select(RepairAttemptModel)
                .where(
                    RepairAttemptModel.run_id == continuation.run_id,
                    RepairAttemptModel.stage_id == continuation.current_stage_id,
                    RepairAttemptModel.status.in_(("applied", "applied_verified")),
                )
                .order_by(RepairAttemptModel.attempt_number.desc())
            )
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
            proposal_raw = json.loads(stored.content)
        except (OSError, ValueError, Exception):
            return False
        is_norm_raw = _proposal_is_normalization(proposal_raw)
        try:
            proposal = RepairProposal.model_validate(proposal_raw)
        except Exception:
            if is_norm_raw:
                return (
                    stored.ref.checksum == attempt.proposal_checksum
                    and stored.envelope is not None
                    and stored.envelope.stage_id == stage_id
                    and stored.envelope.attempt_id == attempt.id
                )
            return False
        if is_norm_raw:
            return (
                stored.ref.checksum == attempt.proposal_checksum
                and stored.envelope is not None
                and stored.envelope.stage_id == stage_id
                and stored.envelope.attempt_id == attempt.id
            )
        return (
            stored.ref.checksum == attempt.proposal_checksum
            and stored.envelope is not None
            and stored.envelope.stage_id == stage_id
            and stored.envelope.attempt_id == attempt.id
            and any(
                item.operation in {"dependency_change", "dependency_add", DEPENDENCY_NORMALIZATION_REPAIR_KIND}
                or (getattr(item, "repair_kind", None) or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
                or (getattr(item, "schema_version", None) or "") == DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
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
        try:
            stage_runtime = TransformerStageService._stage_runtime_rows(session, continuation)
        except TransformerStageError as error:
            raise LockfileGenerationError(error.code, error.message) from error
        if (
            stage_runtime is None
            or execution.runtime_checksum != stage_runtime.get("checksum")
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
        lock_status = validate_generated_lockfile(workspace)
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
            "lockfile_status": lock_status,
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
