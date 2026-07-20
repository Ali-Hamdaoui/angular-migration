"""Application services for G03 Angular transformation, evidence, and G08 acceptance."""

from __future__ import annotations

import difflib
import json
import hashlib
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandLogWriter, CommandPolicy, CommandRegistry, ExecutionWorker
from app.domain.contracts import CancellationPolicy, CommandRequestDto, CommandStatus
from app.domain.contracts import ArtifactRefDto, ArtifactType, RiskLevel, WorkflowEventType
from app.domain.transformation import (
    AngularUpdateCommand,
    AngularUpdateResult,
    AngularUpdateStatus,
    ChangedFileClassification,
    ChangedFileEntry,
    DiffSummary,
    ForbiddenChangeEntry,
    G08ApprovalService,
    G08Decision,
    G08DecisionResult,
    G08EvidencePackage,
    G08EvidencePackageBuilder,
    PackageChangeSummary,
    PromptDetectionResult,
    SensitiveChangeReason,
    TargetVersionEvidence,
    TargetVersionStatus,
    TransformationEvidenceResult,
    VersionEvidenceSource,
)
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel
from app.repositories.models import CommandExecutionModel
from app.repositories.baseline_models import BaselineQualificationModel
from app.repositories.execution_profiles import ExecutionProfileModel
from app.repositories.planning_models import ActivePlanVersionModel, MigrationPlanModel, StageExecutionPlanModel
from app.repositories.planning_review_models import G06ApprovalModel
from app.repositories.session import session_scope
from app.repositories.transformation_models import (
    AngularUpdateRecordModel,
    G08ApprovalModel,
    TransformationEvidenceModel,
)
from app.state.transition_service import StateTransitionService, TransitionRequest


# ── Shared helpers ────────────────────────────────────────────────────────


class G03ApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _write_evidence(
    store: LocalFilesystemArtifactStore,
    session,
    run_id: str,
    name: str,
    payload: dict,
    stage_id: str | None = None,
    *,
    created_by: str = "g03-service",
    created_at: datetime | None = None,
    input_hashes: dict[str, str] | None = None,
) -> ArtifactRefDto:
    now = created_at or datetime.now(UTC)
    stored = store.write_text_artifact(
        run_id,
        f"stage/{stage_id or 'unknown'}/g03/{name}",
        json.dumps(payload, sort_keys=True, indent=2),
        ArtifactType.JSON,
        created_by=created_by,
        created_at=now,
        input_hashes=input_hashes or {},
    )
    metadata = ArtifactMetadataModel(
        id=f"metadata-{stored.ref.artifact_id}",
        run_id=run_id,
        stage_id=stage_id,
        artifact_type=stored.ref.artifact_type.value,
        relative_path=stored.ref.relative_path,
        checksum=stored.ref.checksum,
        created_at=now,
    )
    session.add(metadata)
    return stored.ref


def _register_artifact(session, run_id: str, stage_id: str, stored) -> str:
    """Bind one immutable filesystem artifact to its run and stage."""
    session.add(
        ArtifactMetadataModel(
            id=f"metadata-{stored.ref.artifact_id}",
            run_id=run_id,
            stage_id=stage_id,
            artifact_type=stored.ref.artifact_type.value,
            relative_path=stored.ref.relative_path,
            checksum=stored.ref.checksum,
            created_at=stored.ref.created_at,
        )
    )
    return stored.ref.artifact_id


def _find_event(session, run_id: str, key: str):
    from app.repositories.models import WorkflowEventModel

    return session.scalar(
        select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == run_id,
            WorkflowEventModel.idempotency_key == key,
        )
    )


_INTERACTIVE_PROMPT = re.compile(r"(?im)(?:\[y/n\]|\(y/n\)|yes/no\s*[:?]|(?:continue|proceed|overwrite|confirm|apply|install)[^\n]{0,80}\?\s*$)")
_EXECUTION_LOCK = threading.Lock()


def _prompt_detected(result) -> bool:
    text = "\n".join(item.content for item in (result.stdout_artifact, result.stderr_artifact) if item is not None)
    return bool(_INTERACTIVE_PROMPT.search(text))


def _version(value: str | None) -> str | None:
    match = re.search(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", value or "")
    return match.group(0) if match else None


def _exact_dependency_version(value: str | None) -> str | None:
    return value if re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", value or "") else None


def _major(value: str | None) -> int | None:
    version = _version(value)
    return int(version.split(".", 1)[0]) if version else None


def _tree_checksum(root: Path) -> str:
    digest = hashlib.sha256()
    for item in root.rglob("*"):
        if item.is_symlink():
            raise ValueError("symlink in authoritative tree")
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def _package_version(path: Path, package_name: str) -> str | None:
    try:
        package = json.loads((path / "package.json").read_text(encoding="utf-8"))
        return _exact_dependency_version((package.get("dependencies") or {}).get(package_name) or (package.get("devDependencies") or {}).get(package_name))
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _lock_version(path: Path, package_name: str) -> str | None:
    try:
        lock = json.loads((path / "package-lock.json").read_text(encoding="utf-8"))
        return _exact_dependency_version(lock.get("packages", {}).get(f"node_modules/{package_name}", {}).get("version"))
    except (OSError, TypeError, json.JSONDecodeError):
        return None


def _installed_version(path: Path, package_name: str) -> str | None:
    try:
        return _exact_dependency_version(json.loads((path / "node_modules" / package_name / "package.json").read_text(encoding="utf-8")).get("version"))
    except (OSError, TypeError, json.JSONDecodeError):
        return None


def _normalize_line_endings(content: bytes) -> bytes:
    return content.replace(b"\r\n", b"\n")


_MAX_DIFF_FILE_SIZE = 50 * 1024 * 1024

_KNOWN_ANGULAR_MIGRATIONS = frozenset({
    "migration-v18", "migration-v17", "migration-v16", "migration-v15",
    "migration-v14", "migration-v13",
})


def _scan_migrations(workspace: Path) -> list[str]:
    migrations: list[str] = []
    angular_dir = workspace / ".angular"
    if angular_dir.is_dir():
        for item in sorted(angular_dir.glob("migration-*.json")):
            name = item.stem
            if name in _KNOWN_ANGULAR_MIGRATIONS:
                migrations.append(name)
    pkg = workspace / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            for script_name, script_cmd in scripts.items():
                if isinstance(script_cmd, str) and "ng update" in script_cmd:
                    for known in _KNOWN_ANGULAR_MIGRATIONS:
                        if known in script_cmd:
                            migrations.append(known)
        except (OSError, json.JSONDecodeError):
            pass
    # Heuristic: scan cli-output directory for migration names in text and JSON
    cli_output_dir = workspace / ".angular" / "cli-output"
    if cli_output_dir.is_dir():
        for item in sorted(cli_output_dir.rglob("*")):
            if item.is_file():
                try:
                    text = item.read_text(encoding="utf-8", errors="replace")
                    for known in _KNOWN_ANGULAR_MIGRATIONS:
                        if known in text and known not in migrations:
                            migrations.append(known)
                except OSError:
                    pass
        # Try structured JSON parsing for better detection
        for json_file in sorted(cli_output_dir.rglob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict):
                    for key in ("migrations", "applied_migrations", "available_migrations", "migration_notes"):
                        value = data.get(key)
                        if isinstance(value, list):
                            for v in value:
                                if isinstance(v, str) and v in _KNOWN_ANGULAR_MIGRATIONS and v not in migrations:
                                    migrations.append(v)
                        elif isinstance(value, str) and value in _KNOWN_ANGULAR_MIGRATIONS and value not in migrations:
                            migrations.append(value)
            except (OSError, json.JSONDecodeError):
                pass
    # Also check for target-version-report.json in .angular directory
    tv_report = angular_dir / "cli-output" / "target-version-report.json"
    if not tv_report.is_file():
        tv_report = angular_dir / "target-version-report.json"
    if tv_report.is_file():
        try:
            text = tv_report.read_text(encoding="utf-8", errors="replace")
            for known in _KNOWN_ANGULAR_MIGRATIONS:
                if known in text and known not in migrations:
                    migrations.append(known)
        except OSError:
            pass
    return sorted(set(migrations))


# ── S3-F07 — Angular Update Service ──────────────────────────────────────


class AngularUpdateApplicationService:
    def __init__(self, *, session_scope_factory=session_scope, now_provider=None, worker_factory=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._worker_factory = worker_factory

    def get(self, run_id: str, stage_id: str):
        with self._scope() as session:
            record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            if record is None:
                return None
            return self._dto(record)

    def get_target_version(self, run_id: str, stage_id: str):
        with self._scope() as session:
            record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            if record is None:
                return None
            return self._dto_target_version(record)

    def start_update(self, run_id: str, stage_id: str, request) -> object:
        with _EXECUTION_LOCK:
            prepared = self._prepare_execution(run_id, stage_id, request)
            execution_id, command, workspace, runtime_id, runtime_checksum = prepared
            if execution_id is None:
                with self._scope() as session:
                    record = session.scalar(select(AngularUpdateRecordModel).where(AngularUpdateRecordModel.run_id == run_id, AngularUpdateRecordModel.idempotency_key == request.idempotency_key))
                    return self._dto(record, replay=True)
            result = self._execute(run_id, stage_id, request, execution_id, command, workspace, runtime_id, runtime_checksum)
            with self._scope() as session:
                record = session.get(AngularUpdateRecordModel, execution_id.replace("execution-", "ang-upd-", 1))
                if record is None:
                    record = session.scalar(select(AngularUpdateRecordModel).where(AngularUpdateRecordModel.command_execution_id == execution_id))
                return self._dto(record) if record else result

    def _prepare_execution(self, run_id, stage_id, request):
        now = self._now()
        with self._scope() as session:
            run = session.scalar(select(MigrationRunModel).where(MigrationRunModel.id == run_id).with_for_update())
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            request_checksum = "sha256:" + hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            existing = session.scalar(select(AngularUpdateRecordModel).where(AngularUpdateRecordModel.run_id == run_id, AngularUpdateRecordModel.idempotency_key == request.idempotency_key))
            if existing:
                if existing.stage_id != stage_id or (existing.source_version, existing.target_version) != (request.source_version, request.target_version) or (existing.evidence or {}).get("request_checksum") != request_checksum:
                    raise G03ApplicationError("IDEMPOTENCY_PAYLOAD_MISMATCH", "Idempotency key payload differs.", status_code=409)
                if (existing.evidence or {}).get("partial_mutation"):
                    raise G03ApplicationError("PARTIAL_MUTATION_RECOVERY_REQUIRED", "Failed workspace requires recovery or rebuild before retry.", status_code=409)
                current_workspace = Path((run.workspace_aliases or {}).get("STAGE_SANDBOX", ""))
                binding = "sha256:" + hashlib.sha256(json.dumps({"request": request_checksum, "plan": (existing.evidence or {}).get("plan_checksum"), "stage_plan": (existing.evidence or {}).get("stage_plan_checksum"), "profile": (existing.evidence or {}).get("execution_profile_checksum"), "workspace": _tree_checksum(current_workspace.resolve())}, sort_keys=True).encode()).hexdigest()
                if binding != (existing.evidence or {}).get("idempotency_binding"):
                    raise G03ApplicationError("IDEMPOTENCY_BINDING_MISMATCH", "Idempotency binding no longer matches the approved execution context.", status_code=409)
                return None, None, None, None, None
            if run.state_version != request.expected_state_version:
                raise G03ApplicationError("STALE_STATE_VERSION", "Run state version is stale.", status_code=409)
            if not request.prerequisite_artifact_ids:
                raise G03ApplicationError("PREREQUISITE_ARTIFACT_REQUIRED", "Bootstrap and sandbox prerequisite artifacts are required.", status_code=409)
            prerequisite_evidence = self._validate_prerequisites(session, run, stage_id, request.prerequisite_artifact_ids)
            stage_pointer = session.scalar(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == stage_id))
            if stage_pointer is None or stage_pointer.stage_plan_id is None:
                raise G03ApplicationError("PREREQUISITE_PLAN_REQUIRED", "Approved stage plan is required.", status_code=409)
            plan = session.get(MigrationPlanModel, stage_pointer.migration_plan_id)
            stage_plan = session.get(StageExecutionPlanModel, stage_pointer.stage_plan_id)
            gate = session.scalar(select(G06ApprovalModel).where(G06ApprovalModel.run_id == run_id, G06ApprovalModel.gate_id == "G06").order_by(G06ApprovalModel.created_at.desc()))
            if not plan or not stage_plan or not gate or gate.status != "approved" or gate.plan_checksum != plan.checksum or gate.stage_plan_checksum != stage_plan.checksum:
                raise G03ApplicationError("PREREQUISITE_PLAN_CHECKSUM", "Approved plan binding is stale or missing.", status_code=409)
            values = stage_plan.stage_plan
            if values.get("stage_id") != stage_id or values.get("target_exact") != request.target_version or values.get("source_exact") != request.source_version:
                raise G03ApplicationError("PLAN_INPUT_MISMATCH", "Caller versions do not match locked stage plan.", status_code=409)
            if _major(values.get("target_exact")) != _major(values.get("source_exact")) + 1:
                raise G03ApplicationError("ONE_MAJOR_ROUTE_REQUIRED", "Angular update must follow exactly one major-version route.", status_code=409)
            profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.created_at.desc()))
            if not profile or profile.status not in {"resolved", "selected"} or profile.selected_profile_id != values.get("execution_profile_id") or not profile.selected_checksum:
                raise G03ApplicationError("EXECUTION_PROFILE_REQUIRED", "Selected execution profile is missing or stale.", status_code=409)
            baseline = session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == run_id).order_by(BaselineQualificationModel.created_at.desc()))
            if not baseline or baseline.status not in {"qualified", "qualified_with_known_failures"} or baseline.authorization_status != "authorized":
                raise G03ApplicationError("BOOTSTRAP_PREREQUISITE_REQUIRED", "Successful authorized bootstrap evidence is required.", status_code=409)
            workspace_raw = (run.workspace_aliases or {}).get("STAGE_SANDBOX")
            workspace_candidate = Path(workspace_raw) if workspace_raw else None
            workspace = workspace_candidate.resolve() if workspace_candidate else None
            run_root = Path(run.run_root).resolve() if run.run_root else None
            if workspace is None or workspace_candidate.is_symlink() or not workspace.is_dir() or run_root is None or not workspace.is_relative_to(run_root):
                raise G03ApplicationError("WORKSPACE_BOUNDARY", "Registered stage sandbox is missing or unsafe.", status_code=409)
            source_raw = run.source_path or (run.workspace_aliases or {}).get("SOURCE_SNAPSHOT")
            source_candidate = Path(source_raw) if source_raw else None
            source = source_candidate.resolve() if source_candidate else None
            if source is None or source_candidate.is_symlink() or not source.is_dir() or source == workspace or source.is_relative_to(workspace) or workspace.is_relative_to(source):
                raise G03ApplicationError("SOURCE_SAFETY_AUTHORITY_REQUIRED", "Immutable source boundary is missing or overlaps stage sandbox.", status_code=409)
            if any(item.is_symlink() for item in workspace.rglob("*")):
                raise G03ApplicationError("WORKSPACE_BOUNDARY", "Stage sandbox contains a symlink escape.", status_code=409)
            if any(item.is_symlink() for item in source.rglob("*")):
                raise G03ApplicationError("SOURCE_SAFETY_AUTHORITY_REQUIRED", "Immutable source contains a symlink escape.", status_code=409)
            refs = values.get("commands", {}).get("angular_update", ())
            ref = next((item for item in refs if item.get("command_id") == "angular-update"), None)
            if ref is None or ref.get("executable") not in {"npx", "npx.cmd"} or ref.get("shell") is not False:
                raise G03ApplicationError("INCOMPATIBLE_PLAN_COMMAND", "Locked plan has no approved local Angular CLI command.", status_code=409)
            arguments = list(ref.get("arguments", ()))
            expected_cli = values.get("target_cli_exact") or values["target_exact"]
            expected_arguments = ["--no-install", "ng", "update", f"@angular/core@{values['target_exact']}", f"@angular/cli@{expected_cli}"]
            if arguments != expected_arguments:
                raise G03ApplicationError("INCOMPATIBLE_PLAN_COMMAND", "Forbidden Angular command flags are not allowed.", status_code=409)
            command_id = f"execution-{uuid4().hex[:12]}"
            transition = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=run.state_version, idempotency_key=request.idempotency_key, event_type=WorkflowEventType.ANGULAR_UPDATE_STARTED, actor=request.actor, reason="approved Angular update started", occurred_at=now, stage_id=stage_id, payload={"plan_checksum": stage_plan.checksum, "stage_plan_checksum": stage_plan.checksum, "command_execution_id": command_id}))
            workspace_fingerprint = _tree_checksum(workspace)
            idempotency_binding = "sha256:" + hashlib.sha256(json.dumps({"request": request_checksum, "plan": plan.checksum, "stage_plan": stage_plan.checksum, "profile": profile.selected_checksum, "workspace": workspace_fingerprint}, sort_keys=True).encode()).hexdigest()
            record = AngularUpdateRecordModel(id=f"ang-upd-{uuid4().hex[:12]}", run_id=run_id, stage_id=stage_id, idempotency_key=request.idempotency_key, actor=request.actor, status=AngularUpdateStatus.RUNNING.value, target_version_status=TargetVersionStatus.INCONCLUSIVE.value, source_version=values["source_exact"], target_version=values["target_exact"], command_execution_id=command_id, prompt_detected=PromptDetectionResult.NO_PROMPT.value, evidence={"request_checksum": request_checksum, "plan_checksum": plan.checksum, "stage_plan_checksum": stage_plan.checksum, "execution_profile_id": profile.selected_profile_id, "execution_profile_checksum": profile.selected_checksum, "expected_cli_target": expected_cli, "workspace_fingerprint": workspace_fingerprint, "source_fingerprint": _tree_checksum(source), "source_path": str(source), "prerequisite_artifacts": prerequisite_evidence, "idempotency_binding": idempotency_binding}, artifact_ids=[], state_version=transition.next_state_version, event_sequence=transition.event_sequence, created_at=now, updated_at=now)
            session.add(record)
            session.add(CommandExecutionModel(id=command_id, run_id=run_id, stage_id=stage_id, idempotency_key=request.idempotency_key + ":command", requested_by=request.actor, requester=request.actor, executable="npx", arguments=arguments, working_directory_alias="STAGE_SANDBOX", runtime_profile_id=profile.selected_profile_id, runtime_checksum=profile.selected_checksum, command_id="angular-update", shell=False, timeout_seconds=int(ref.get("timeout_seconds", 600)), network_profile=ref.get("network_profile", "none"), cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE.value, status=CommandStatus.PENDING.value, requested_at=now, artifact_ids=[], blockers=[], state_version=transition.next_state_version, event_sequence=transition.event_sequence))
            session.flush()
            return command_id, AngularUpdateCommand(executable="npx", arguments=arguments, working_directory_alias="STAGE_SANDBOX", timeout_seconds=int(ref.get("timeout_seconds", 600)), network_profile=ref.get("network_profile", "none")), workspace, profile.selected_profile_id, profile.selected_checksum

    def _validate_prerequisites(self, session, run, stage_id, artifact_ids):
        store = LocalFilesystemArtifactStore(Path(run.artifact_root).resolve(), fixed_run_root=Path(run.artifact_root).resolve())
        found = {"sandbox": False, "bootstrap": False, "source": False}
        evidence = []
        for artifact_id in artifact_ids:
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
            if metadata is None:
                raise G03ApplicationError("PREREQUISITE_ARTIFACT_MISSING", "A prerequisite artifact is not registered.", status_code=409)
            if metadata.run_id != run.id or metadata.stage_id != stage_id:
                raise G03ApplicationError("PREREQUISITE_ARTIFACT_OWNERSHIP", "A prerequisite artifact belongs to another run or stage.", status_code=409)
            try:
                artifact = store.read_artifact_by_id(artifact_id)
            except (OSError, ValueError, KeyError) as error:
                raise G03ApplicationError("PREREQUISITE_ARTIFACT_MISSING", "A prerequisite artifact cannot be read.", status_code=409) from error
            if artifact.ref.checksum != metadata.checksum:
                raise G03ApplicationError("PREREQUISITE_ARTIFACT_CHECKSUM", "A prerequisite artifact checksum does not match.", status_code=409)
            try:
                payload = json.loads(artifact.content)
            except (TypeError, json.JSONDecodeError):
                payload = {}
            name = metadata.relative_path.lower()
            found["sandbox"] |= "sandbox" in name and payload.get("status") in {"ready", "passed"}
            found["bootstrap"] |= "bootstrap" in name and payload.get("install_status", payload.get("status")) in {"passed", "succeeded"}
            found["source"] |= "source" in name and payload.get("status") == "unchanged"
            evidence.append({"artifact_id": artifact_id, "checksum": metadata.checksum, "stage_id": metadata.stage_id})
        if not found["sandbox"]:
            raise G03ApplicationError("G07_SANDBOX_AUTHORITY_REQUIRED", "Authoritative G07 sandbox evidence is required.", status_code=409)
        if not found["bootstrap"]:
            raise G03ApplicationError("BOOTSTRAP_AUTHORITY_REQUIRED", "Successful stage bootstrap evidence is required.", status_code=409)
        if not found["source"]:
            raise G03ApplicationError("SOURCE_INTEGRITY_AUTHORITY_REQUIRED", "Source immutability evidence is required.", status_code=409)
        return evidence

    def _execute(self, run_id, stage_id, request, execution_id, command, workspace, runtime_id, runtime_checksum):
        if not execution_id:
            return None
        root = workspace.parent
        store = LocalFilesystemArtifactStore(Path(self._run_artifact_root(run_id)), fixed_run_root=Path(self._run_artifact_root(run_id)))
        worker = self._worker_factory(run_id, workspace, runtime_id, runtime_checksum) if self._worker_factory else ExecutionWorker(CommandPolicy(sandbox_root=root, registry=CommandRegistry(), working_directory_aliases={"STAGE_SANDBOX": workspace}, runtime_profiles=frozenset({runtime_id}), network_profiles=frozenset({command.network_profile})), CommandLogWriter(store))
        command_request = CommandRequestDto(command_id="angular-update", run_id=run_id, stage_id=stage_id, requested_by=request.actor, requester=request.actor, executable=command.executable, arguments=command.arguments, working_directory_alias="STAGE_SANDBOX", runtime_profile_id=runtime_id, shell=False, timeout_seconds=command.timeout_seconds, network_profile=command.network_profile, cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE, idempotency_key=request.idempotency_key + ":command", requested_at=self._now())
        cancel_event = threading.Event()
        try:
            result = worker.run(command_request, cancel_event=cancel_event, output_callback=lambda _stream, chunk: cancel_event.set() if _INTERACTIVE_PROMPT.search(chunk) else None)
        except Exception as error:
            self._mark_command_start_failure(run_id, stage_id, execution_id, request, error)
            raise G03ApplicationError("COMMAND_START_FAILED", "Approved Angular command could not start.", status_code=409) from error
        with self._scope() as session:
            record = session.scalar(select(AngularUpdateRecordModel).where(AngularUpdateRecordModel.command_execution_id == execution_id))
            execution = session.get(CommandExecutionModel, execution_id)
            record.command_execution_id = execution_id
            stored_artifacts = [item for item in (result.command_log_artifact, result.stdout_artifact, result.stderr_artifact) if item]
            artifact_ids = [_register_artifact(session, run_id, stage_id, item) for item in stored_artifacts]
            prompt = _prompt_detected(result)
            workspace_before = (record.evidence or {}).get("workspace_fingerprint")
            workspace_after = _tree_checksum(workspace)
            source_path = Path((record.evidence or {}).get("source_path", ""))
            source_before = (record.evidence or {}).get("source_fingerprint")
            source_after = _tree_checksum(source_path) if source_path.is_dir() else None
            source_changed = source_before is not None and source_after != source_before
            workspace_changed = workspace_after != workspace_before
            verified = False
            evidence = dict(record.evidence or {})
            version_result = None
            if result.result.status is CommandStatus.SUCCEEDED and not prompt:
                version_request = command_request.model_copy(update={"command_id": "angular-version", "arguments": ["ng", "version"], "idempotency_key": request.idempotency_key + ":version"})
                version_result = worker.run(version_request)
                stored_artifacts.extend(item for item in (version_result.command_log_artifact, version_result.stdout_artifact, version_result.stderr_artifact) if item)
                ng_output = "\n".join(item.content for item in (version_result.stdout_artifact, version_result.stderr_artifact) if item is not None)
                tree_request = command_request.model_copy(update={"command_id": "angular-dependency-tree", "executable": "npm", "arguments": ["ls", "--json", "--depth=0"], "idempotency_key": request.idempotency_key + ":tree"})
                tree_result = worker.run(tree_request)
                stored_artifacts.extend(item for item in (tree_result.command_log_artifact, tree_result.stdout_artifact, tree_result.stderr_artifact) if item)
                tree_output = "\n".join(item.content for item in (tree_result.stdout_artifact, tree_result.stderr_artifact) if item is not None)
                try:
                    dependency_tree = json.loads(tree_output)
                except (TypeError, json.JSONDecodeError):
                    dependency_tree = {}
                tree_core = _exact_dependency_version((dependency_tree.get("dependencies") or {}).get("@angular/core", {}).get("version"))
                tree_cli = _exact_dependency_version((dependency_tree.get("dependencies") or {}).get("@angular/cli", {}).get("version"))
                package = _package_version(workspace, "@angular/core")
                cli = _package_version(workspace, "@angular/cli")
                lock_core = _lock_version(workspace, "@angular/core")
                lock_cli = _lock_version(workspace, "@angular/cli")
                expected = record.target_version
                expected_cli = (record.evidence or {}).get("expected_cli_target", expected)
                evidence.update({"package_json_core": package, "package_json_cli": cli, "lockfile_core": lock_core, "lockfile_cli": lock_cli, "dependency_tree_core": tree_core, "dependency_tree_cli": tree_cli, "ng_version": CommandLogWriter._redact(ng_output), "execution_profile_id": runtime_id, "execution_profile_checksum": runtime_checksum, "expected_cli_target": expected_cli})
                versions = [package, cli, lock_core, lock_cli, tree_core, tree_cli, _version(re.search(r"Angular:\s*([^\s]+)", ng_output, re.I).group(1) if re.search(r"Angular:\s*([^\s]+)", ng_output, re.I) else None), _version(re.search(r"Angular CLI:\s*([^\s]+)", ng_output, re.I).group(1) if re.search(r"Angular CLI:\s*([^\s]+)", ng_output, re.I) else None)]
                verified = version_result.result.status is CommandStatus.SUCCEEDED and tree_result.result.status is CommandStatus.SUCCEEDED and all(value == expected for value in versions[:1] + versions[2:]) and cli == expected_cli and lock_cli == expected_cli and tree_cli == expected_cli and versions[-1] == expected_cli
                evidence["all_sources_agree"] = verified
                evidence["disagreements"] = [] if verified else [name for name, value in {"package_json_core": package, "package_json_cli": cli, "lockfile_core": lock_core, "lockfile_cli": lock_cli, "dependency_tree_core": tree_core, "dependency_tree_cli": tree_cli}.items() if value is None or value != (expected_cli if name.endswith("cli") else expected)]
                for name, content, artifact_type in (("package_json", workspace / "package.json", ArtifactType.JSON), ("package_lock", workspace / "package-lock.json", ArtifactType.JSON)):
                    if content.is_file():
                        stored = store.write_text_artifact(run_id, f"stage/{stage_id}/angular-update/{name}{content.suffix}", content.read_text(encoding="utf-8"), artifact_type, stage_id=stage_id, created_by="angular-update-service", created_at=self._now(), input_hashes={"workspace": workspace_after})
                        stored_artifacts.append(stored)
                report = store.write_text_artifact(run_id, f"stage/{stage_id}/angular-update/target-version-report.json", json.dumps({"target_version": expected, "evidence": evidence, "migrations": _scan_migrations(workspace)}, sort_keys=True, indent=2), ArtifactType.REPORT, stage_id=stage_id, created_by="angular-update-service", created_at=self._now(), input_hashes={"workspace": workspace_after})
                stored_artifacts.append(report)
                if not verified:
                    record.error_message = "EXACT_TARGET_MISMATCH"
            for item in stored_artifacts:
                if item.ref.artifact_id not in artifact_ids:
                    artifact_ids.append(_register_artifact(session, run_id, stage_id, item))
            record.artifact_ids = artifact_ids
            partial_mutation = source_changed or (workspace_changed and (result.result.status is not CommandStatus.SUCCEEDED or not verified))
            record.status = AngularUpdateStatus.SUCCEEDED.value if result.result.status is CommandStatus.SUCCEEDED and verified and not prompt and not source_changed else AngularUpdateStatus.FAILED.value
            record.target_version_status = TargetVersionStatus.VERIFIED.value if verified else TargetVersionStatus.MISMATCH.value
            record.resolved_target_version = record.target_version if verified else None
            evidence.update({"workspace_fingerprint_before": workspace_before, "workspace_fingerprint_after": workspace_after, "source_fingerprint_before": source_before, "source_fingerprint_after": source_after, "partial_mutation": partial_mutation, "source_changed": source_changed})
            record.evidence = evidence
            failure_code = "TIMEOUT" if result.timed_out else "CANCELLATION" if result.cancelled else "EXIT_NONZERO" if result.result.status is CommandStatus.FAILED else "ANGULAR_UPDATE_EXECUTION_FAILED"
            record.error_message = "SOURCE_MUTATION_DETECTED" if source_changed else "PARTIAL_MUTATION" if partial_mutation else "INTERACTIVE_PROMPT_DETECTED" if prompt else record.error_message or (None if record.status == AngularUpdateStatus.SUCCEEDED.value else failure_code)
            if partial_mutation:
                record.evidence["partial_mutation"] = True
            record.prompt_detected = PromptDetectionResult.PROMPT_DETECTED.value if prompt else PromptDetectionResult.NO_PROMPT.value
            execution.status = result.result.status.value
            execution.started_at, execution.finished_at, execution.exit_code = result.result.started_at, result.result.finished_at, result.result.exit_code
            execution.timed_out, execution.cancelled = result.timed_out, result.cancelled
            execution.command_log_artifact_id = result.command_log_artifact.ref.artifact_id
            execution.stdout_artifact_id = result.stdout_artifact.ref.artifact_id if result.stdout_artifact else None
            execution.stderr_artifact_id = result.stderr_artifact.ref.artifact_id if result.stderr_artifact else None
            run = session.get(MigrationRunModel, run_id)
            if prompt:
                prompt_transition = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=run.state_version, idempotency_key=request.idempotency_key + ":prompt", event_type=WorkflowEventType.INTERACTIVE_DECISION_REQUIRED, actor=request.actor, reason="Unexpected interactive prompt blocked execution", occurred_at=self._now(), stage_id=stage_id, payload={"execution_id": execution_id, "reason_code": "INTERACTIVE_PROMPT_DETECTED"}))
                run = session.get(MigrationRunModel, run_id)
            target_event = WorkflowEventType.TARGET_VERSION_VERIFIED if verified else WorkflowEventType.TARGET_VERSION_FAILED
            target_transition = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=run.state_version, idempotency_key=request.idempotency_key + ":target", event_type=target_event, actor=request.actor, reason="Angular target verification finalized", occurred_at=self._now(), stage_id=stage_id, payload={"execution_id": execution_id, "verified": verified, "evidence": evidence}))
            event_type = WorkflowEventType.ANGULAR_UPDATE_COMPLETED if record.status == AngularUpdateStatus.SUCCEEDED.value else WorkflowEventType.ANGULAR_UPDATE_FAILED
            transition = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=target_transition.next_state_version, idempotency_key=request.idempotency_key + ":completed", event_type=event_type, actor=request.actor, reason="Angular update execution finalized", occurred_at=self._now(), stage_id=stage_id, payload={"execution_id": execution_id, "status": record.status, "error_code": record.error_message}))
            record.state_version, record.event_sequence = transition.next_state_version, transition.event_sequence
            session.flush()
        return result

    def _mark_command_start_failure(self, run_id, stage_id, execution_id, request, error):
        with self._scope() as session:
            record = session.scalar(select(AngularUpdateRecordModel).where(AngularUpdateRecordModel.command_execution_id == execution_id))
            execution = session.get(CommandExecutionModel, execution_id)
            if record is None or execution is None:
                return
            record.status = AngularUpdateStatus.FAILED.value
            record.target_version_status = TargetVersionStatus.MISMATCH.value
            record.error_message = "COMMAND_START_FAILED"
            record.evidence = {**(record.evidence or {}), "command_start_error": type(error).__name__}
            execution.status = CommandStatus.FAILED.value
            run = session.get(MigrationRunModel, run_id)
            transition = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=run.state_version, idempotency_key=request.idempotency_key + ":start-failed", event_type=WorkflowEventType.ANGULAR_UPDATE_FAILED, actor=request.actor, reason="Angular command failed to start", occurred_at=self._now(), stage_id=stage_id, payload={"execution_id": execution_id, "error_code": "COMMAND_START_FAILED"}))
            target = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=transition.next_state_version, idempotency_key=request.idempotency_key + ":start-target", event_type=WorkflowEventType.TARGET_VERSION_FAILED, actor=request.actor, reason="Angular target verification blocked by command start failure", occurred_at=self._now(), stage_id=stage_id, payload={"execution_id": execution_id, "error_code": "COMMAND_START_FAILED"}))
            record.state_version, record.event_sequence = target.next_state_version, target.event_sequence
            session.flush()

    def _run_artifact_root(self, run_id):
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if not run or not run.artifact_root:
                raise G03ApplicationError("ARTIFACT_ROOT_REQUIRED", "Run artifact root is unavailable.", status_code=409)
            return run.artifact_root

    def complete_update(
        self,
        run_id: str,
        stage_id: str,
        request,
        *,
        succeeded: bool = True,
        resolved_version: str | None = None,
        error_message: str | None = None,
    ) -> object:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            if record is None:
                raise G03ApplicationError(
                    "NO_ACTIVE_UPDATE", "No active Angular update for this stage.", status_code=409
                )

            if _find_event(session, run_id, request.idempotency_key) is not None:
                return self._dto(record, replay=True)

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError(
                    "STALE_STATE_VERSION",
                    f"run is at version {run.state_version}, expected {request.expected_state_version}",
                    status_code=409,
                )

            if succeeded:
                execution = session.get(CommandExecutionModel, request.command_execution_id)
                if execution is None or execution.run_id != run_id or execution.stage_id != stage_id or record.command_execution_id != execution.id:
                    raise G03ApplicationError("COMMAND_AUTHORITY_REQUIRED", "The completion command is not authoritative for this update.", status_code=409)
                if execution.status != CommandStatus.SUCCEEDED.value or execution.exit_code != 0:
                    raise G03ApplicationError("COMMAND_NOT_SUCCESSFUL", "Only a successful authoritative command may complete the update.", status_code=409)
                if not record.artifact_ids:
                    raise G03ApplicationError("EVIDENCE_ARTIFACTS_REQUIRED", "Registered command evidence is required before completion.", status_code=409)
                store = LocalFilesystemArtifactStore(Path(run.artifact_root).resolve(), fixed_run_root=Path(run.artifact_root).resolve())
                for artifact_id in record.artifact_ids:
                    metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
                    if metadata is None or metadata.run_id != run_id or metadata.stage_id != stage_id:
                        raise G03ApplicationError("EVIDENCE_ARTIFACT_AUTHORITY", "Completion evidence is not owned by this run and stage.", status_code=409)
                    try:
                        artifact = store.read_artifact_by_id(artifact_id)
                    except (OSError, ValueError, KeyError) as error:
                        raise G03ApplicationError("EVIDENCE_ARTIFACT_MISSING", "Completion evidence cannot be recovered.", status_code=409) from error
                    if artifact.ref.checksum != metadata.checksum:
                        raise G03ApplicationError("EVIDENCE_ARTIFACT_CHECKSUM", "Completion evidence checksum is invalid.", status_code=409)
                if record.target_version_status != TargetVersionStatus.VERIFIED.value:
                    raise G03ApplicationError("TARGET_VERSION_NOT_VERIFIED", "Exact target-version proof is required before completion.", status_code=409)

            event_type = (
                WorkflowEventType.ANGULAR_UPDATE_COMPLETED
                if succeeded
                else WorkflowEventType.ANGULAR_UPDATE_FAILED
            )

            record.status = AngularUpdateStatus.SUCCEEDED.value if succeeded else AngularUpdateStatus.FAILED.value
            record.resolved_target_version = resolved_version
            record.error_message = error_message
            record.updated_at = now
            session.flush()
            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=event_type,
                    actor=request.actor,
                    reason=f"Angular update {'completed' if succeeded else 'failed'}",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={"succeeded": succeeded, "resolved_version": resolved_version, "stage_id": stage_id},
                )
            )
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            session.flush()

            return self._dto(record)

    def verify_target_version(
        self,
        run_id: str,
        stage_id: str,
        request,
        *,
        evidence: TargetVersionEvidence | None = None,
    ) -> object:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            if record is None:
                raise G03ApplicationError(
                    "NO_ACTIVE_UPDATE", "No Angular update record for this stage.", status_code=404
                )

            if _find_event(session, run_id, request.idempotency_key) is not None:
                return self._dto_target_version(record, replay=True)

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError(
                    "STALE_STATE_VERSION",
                    f"run is at version {run.state_version}, expected {request.expected_state_version}",
                    status_code=409,
                )

            execution = session.get(CommandExecutionModel, request.command_execution_id)
            if execution is None or execution.run_id != run_id or execution.stage_id != stage_id or record.command_execution_id != execution.id:
                raise G03ApplicationError("COMMAND_AUTHORITY_REQUIRED", "The verification command is not authoritative for this update.", status_code=409)
            if execution.status != CommandStatus.SUCCEEDED.value or execution.exit_code != 0:
                raise G03ApplicationError("COMMAND_NOT_SUCCESSFUL", "Only a successful authoritative command may verify the target.", status_code=409)
            if evidence is None:
                persisted = record.evidence or {}
                ev = TargetVersionEvidence(
                    package_json_version=persisted.get("package_json_core") or persisted.get("package_json_version"),
                    lockfile_version=persisted.get("lockfile_core") or persisted.get("lockfile_version"),
                    ng_version_output=persisted.get("ng_version") or persisted.get("ng_version_output"),
                    dependency_tree_version=persisted.get("dependency_tree_core") or persisted.get("dependency_tree_version"),
                    resolved_target=record.resolved_target_version or record.target_version,
                    all_sources_agree=persisted.get("all_sources_agree", False),
                    disagreements=persisted.get("disagreements", []),
                )
            else:
                ev = evidence
            required_sources = (ev.package_json_version, ev.lockfile_version, ev.ng_version_output, ev.dependency_tree_version)
            verified = ev.all_sources_agree and ev.resolved_target == record.target_version and all(required_sources)
            event_type = (
                WorkflowEventType.TARGET_VERSION_VERIFIED
                if verified
                else WorkflowEventType.TARGET_VERSION_FAILED
            )

            record.target_version_status = TargetVersionStatus.VERIFIED.value if verified else TargetVersionStatus.MISMATCH.value
            record.resolved_target_version = ev.resolved_target if verified else None
            record.evidence = ev.model_dump(mode="json")
            record.updated_at = now
            session.flush()
            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=event_type,
                    actor=request.actor,
                    reason=f"Target version {'verified' if verified else 'mismatch'}",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={"verified": verified, "resolved_target": ev.resolved_target, "stage_id": stage_id},
                )
            )
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            session.flush()

            return self._dto_target_version(record)

    def _dto(self, record, *, replay=False):
        from app.api.transformation_contracts import AngularUpdateResponse

        return AngularUpdateResponse(
            run_id=record.run_id,
            stage_id=record.stage_id,
            status=AngularUpdateStatus(record.status),
            target_version_status=TargetVersionStatus(record.target_version_status),
            resolved_target_version=record.resolved_target_version,
            command_execution_id=record.command_execution_id,
            prompt_detected=record.prompt_detected,
            artifact_ids=record.artifact_ids,
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            error_message=record.error_message,
            idempotent_replay=replay,
        )

    def _dto_target_version(self, record, *, replay=False):
        from app.api.transformation_contracts import TargetVersionResponse

        evidence = record.evidence or {}
        return TargetVersionResponse(
            run_id=record.run_id,
            stage_id=record.stage_id,
            target_version_status=TargetVersionStatus(record.target_version_status),
            resolved_target_version=record.resolved_target_version,
            evidence_sources={
                "package_json_version": evidence.get("package_json_core") or evidence.get("package_json_version") or "",
                "lockfile_version": evidence.get("lockfile_core") or evidence.get("lockfile_version") or "",
                "ng_version_output": evidence.get("ng_version") or evidence.get("ng_version_output") or "",
                "dependency_tree_version": evidence.get("dependency_tree_core") or evidence.get("dependency_tree_version") or "",
            },
            all_sources_agree=evidence.get("all_sources_agree", False),
            disagreements=evidence.get("disagreements", []),
            artifact_ids=record.artifact_ids,
        )


# ── S3-F08 — Transformation Evidence Service ─────────────────────────────


class TransformationEvidenceApplicationService:
    GATE_VERSION = "g03-evidence-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, stage_id: str):
        with self._scope() as session:
            record = session.scalar(
                select(TransformationEvidenceModel)
                .where(TransformationEvidenceModel.run_id == run_id)
                .where(TransformationEvidenceModel.stage_id == stage_id)
                .order_by(TransformationEvidenceModel.created_at.desc())
            )
            if record is None:
                return None
            return self._dto(record)

    def generate(self, run_id: str, stage_id: str, request) -> object:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            request_checksum = "sha256:" + hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

            existing_event = _find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(
                    select(TransformationEvidenceModel)
                    .where(TransformationEvidenceModel.run_id == run_id)
                    .where(TransformationEvidenceModel.idempotency_key == request.idempotency_key)
                    .order_by(TransformationEvidenceModel.created_at.desc())
                )
                if record is not None and record.request_checksum is not None and record.request_checksum != request_checksum:
                    raise G03ApplicationError("IDEMPOTENCY_PAYLOAD_MISMATCH", "Idempotency key payload differs.", status_code=409)
                return self._dto(record, replay=True) if record else None

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError(
                    "STALE_STATE_VERSION",
                    f"run is at version {run.state_version}, expected {request.expected_state_version}",
                    status_code=409,
                )

            # Source safety checks
            source_candidate = Path(request.source_sandbox_path)
            target_candidate = Path(request.target_sandbox_path)
            source = source_candidate.resolve() if source_candidate else None
            target = target_candidate.resolve() if target_candidate else None
            run_root = Path(run.run_root).resolve() if run.run_root else None
            if source is None or source_candidate.is_symlink() or not source.is_dir():
                raise G03ApplicationError("SOURCE_SAFETY_AUTHORITY_REQUIRED", "Source sandbox path is missing or unsafe.", status_code=409)
            if target is None or target_candidate.is_symlink() or not target.is_dir():
                raise G03ApplicationError("TARGET_SAFETY_AUTHORITY_REQUIRED", "Target sandbox path is missing or unsafe.", status_code=409)
            if source == target or source.is_relative_to(target) or target.is_relative_to(source):
                raise G03ApplicationError("SANDBOX_OVERLAP", "Source and target sandboxes must not overlap.", status_code=409)
            if run_root is not None:
                if not source.is_relative_to(run_root) or not target.is_relative_to(run_root):
                    raise G03ApplicationError("SANDBOX_BOUNDARY", "Sandbox paths must be within the run root.", status_code=409)
            if any(item.is_symlink() for item in source.rglob("*")):
                raise G03ApplicationError("SOURCE_SAFETY_AUTHORITY_REQUIRED", "Source sandbox contains a symlink escape.", status_code=409)
            if any(item.is_symlink() for item in target.rglob("*")):
                raise G03ApplicationError("TARGET_SAFETY_AUTHORITY_REQUIRED", "Target sandbox contains a symlink escape.", status_code=409)

            input_fingerprint = _tree_checksum(source)
            target_fingerprint = _tree_checksum(target)

            # Emit STARTED event before computation
            started_transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key + ":started",
                    event_type=WorkflowEventType.TRANSFORMATION_EVIDENCE_STARTED,
                    actor=request.actor,
                    reason="Transformation evidence computation started",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={"stage_id": stage_id, "source_sandbox_path": str(source), "target_sandbox_path": str(target)},
                )
            )

            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root), fixed_run_root=Path(run.artifact_root)
            ) if run.artifact_root else None

            # Build transformation evidence
            diff_result = self._compute_diff_summary(source, target)

            package_result = self._compute_package_changes(source, target)

            forbidden = self._scan_forbidden_changes(diff_result, package_result)

            migration_list = _scan_migrations(target)

            # Compute unified diff
            unified_diff = self._compute_unified_diff(source, target, diff_result.changed_files)

            diff_written = False
            package_written = False
            migration_written = False
            forbidden_written = False
            inventory_written = False
            artifact_ids: list[str] = []
            if store:
                ref = _write_evidence(
                    store, session, run_id, "transformation_diff_summary.json",
                    diff_result.model_dump(mode="json"),
                    stage_id=stage_id,
                    created_by="transformation-evidence-service",
                    created_at=now,
                    input_hashes={"diff_checksum": diff_result.diff_checksum},
                )
                artifact_ids.append(ref.artifact_id)

                if package_result:
                    ref2 = _write_evidence(
                        store, session, run_id, "package_change_summary.json",
                        package_result.model_dump(mode="json"),
                        stage_id=stage_id,
                        created_by="transformation-evidence-service",
                        created_at=now,
                    )
                    artifact_ids.append(ref2.artifact_id)
                    package_written = True

                if forbidden:
                    ref3 = _write_evidence(
                        store, session, run_id, "forbidden_changes.json",
                        {"forbidden_changes": [f.model_dump(mode="json") for f in forbidden]},
                        stage_id=stage_id,
                        created_by="transformation-evidence-service",
                        created_at=now,
                    )
                    artifact_ids.append(ref3.artifact_id)
                    forbidden_written = True

                # Write unified diff artifact
                if unified_diff:
                    diff_ref = _write_evidence(
                        store, session, run_id, "transformation_diff.patch",
                        {"patch": unified_diff},
                        stage_id=stage_id,
                        created_by="transformation-evidence-service",
                        created_at=now,
                        input_hashes={"diff_checksum": diff_result.diff_checksum},
                    )
                    artifact_ids.append(diff_ref.artifact_id)
                    diff_written = True

                # Register standalone migration list artifact
                mig_ref = _write_evidence(
                    store, session, run_id, "transformation_migration_list.json",
                    {"migrations": migration_list},
                    stage_id=stage_id,
                    created_by="transformation-evidence-service",
                    created_at=now,
                )
                artifact_ids.append(mig_ref.artifact_id)
                migration_written = True

                # Register standalone changed file inventory artifact
                inv_payload = {
                    "total_files_changed": diff_result.total_files_changed,
                    "changed_files": [cf.model_dump(mode="json") for cf in diff_result.changed_files],
                }
                inv_ref = _write_evidence(
                    store, session, run_id, "transformation_changed_file_inventory.json",
                    inv_payload,
                    stage_id=stage_id,
                    created_by="transformation-evidence-service",
                    created_at=now,
                )
                artifact_ids.append(inv_ref.artifact_id)
                inventory_written = True

            overall_risk = self._compute_overall_risk(diff_result, forbidden)
            checks = []
            checks.append(diff_written)
            checks.append(migration_written)
            checks.append(inventory_written)
            if package_result:
                checks.append(package_written)
            if forbidden:
                checks.append(forbidden_written)
            evidence_complete = all(checks) if store else False

            event_type = (
                WorkflowEventType.TRANSFORMATION_EVIDENCE_COMPLETED
                if evidence_complete
                else WorkflowEventType.TRANSFORMATION_EVIDENCE_BLOCKED
            )

            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=started_transition.next_state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=event_type,
                    actor=request.actor,
                    reason=f"Transformation evidence {'completed' if evidence_complete else 'blocked'}",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={
                        "evidence_complete": evidence_complete,
                        "overall_risk_level": overall_risk.value,
                        "stage_id": stage_id,
                        "total_files_changed": diff_result.total_files_changed,
                    },
                )
            )

            record_id = f"tev-{uuid4().hex[:12]}"
            record = TransformationEvidenceModel(
                id=record_id,
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                status="completed" if evidence_complete else "blocked",
                overall_risk_level=overall_risk.value,
                total_files_changed=diff_result.total_files_changed,
                diff_checksum=diff_result.diff_checksum,
                diff_summary=diff_result.model_dump(mode="json"),
                package_change_summary=package_result.model_dump(mode="json") if package_result else None,
                migration_list=migration_list,
                forbidden_changes=[f.model_dump(mode="json") for f in forbidden],
                changed_file_classifications={
                    cf.file_path: cf.classification.value for cf in diff_result.changed_files
                },
                evidence_complete=evidence_complete,
                artifact_ids=artifact_ids,
                state_version=transition.next_state_version,
                event_sequence=transition.event_sequence,
                block_reason=None if evidence_complete else "No changes detected in transformation sandbox",
                correlation_id=request.correlation_id,
                input_fingerprint=input_fingerprint,
                target_fingerprint=target_fingerprint,
                request_checksum=request_checksum,
                gate_version=self.GATE_VERSION,
                source_sandbox_path=str(source),
                target_sandbox_path=str(target),
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()

            return self._dto(record, source_sandbox_path=str(source), target_sandbox_path=str(target))

    def _compute_diff_summary(self, source_path: Path, target_path: Path) -> DiffSummary:
        """Compute a diff summary by comparing files between source and target sandboxes."""
        changed_files: list[ChangedFileEntry] = []
        total_added = 0
        total_removed = 0
        checksum_input: list[str] = []

        if not source_path.exists() or not target_path.exists():
            return DiffSummary(
                total_files_changed=0,
                total_lines_added=0,
                total_lines_removed=0,
                changed_files=[],
                diff_checksum="sha256:" + "0" * 64,
            )

        source_files = {p.relative_to(source_path): p for p in source_path.rglob("*") if p.is_file()}
        target_files = {p.relative_to(target_path): p for p in target_path.rglob("*") if p.is_file()}
        all_paths = set(source_files) | set(target_files)

        for rel_path in sorted(all_paths):
            sp = source_files.get(rel_path)
            tp = target_files.get(rel_path)
            path_str = str(rel_path)

            # Large file safety: skip reading files > 50MB
            size_bytes = 0
            if tp:
                size_bytes = tp.stat().st_size
            elif sp:
                size_bytes = sp.stat().st_size
            if (sp and sp.stat().st_size > _MAX_DIFF_FILE_SIZE) or (tp and tp.stat().st_size > _MAX_DIFF_FILE_SIZE):
                if sp and tp:
                    change_type = "modified"
                elif sp:
                    change_type = "deleted"
                else:
                    change_type = "added"
                added = 0
                removed = 0
                classification = ChangedFileClassification.GENERATED
                reason = SensitiveChangeReason.GENERATED_FILE
                total_added += added
                total_removed += removed
                checksum_input.append(f"{change_type}:{path_str}:{added}:{removed}")
                changed_files.append(
                    ChangedFileEntry(
                        file_path=path_str,
                        change_type=change_type,
                        classification=classification,
                        reason=reason,
                        lines_added=added,
                        lines_removed=removed,
                        is_binary=False,
                        is_generated=True,
                        size_bytes=size_bytes,
                    )
                )
                continue

            if sp and tp:
                try:
                    sc = _normalize_line_endings(sp.read_bytes())
                    tc = _normalize_line_endings(tp.read_bytes())
                    if sc == tc:
                        continue  # unchanged
                    change_type = "modified"
                    sc_lines = sc.splitlines()
                    tc_lines = tc.splitlines()
                    added = max(0, len(tc_lines) - len(sc_lines))
                    removed = max(0, len(sc_lines) - len(tc_lines))
                except OSError:
                    continue
            elif sp and not tp:
                change_type = "deleted"
                added = 0
                try:
                    removed = len(_normalize_line_endings(sp.read_bytes()).splitlines())
                except (OSError, UnicodeDecodeError):
                    removed = 0
            else:
                change_type = "added"
                removed = 0
                try:
                    added = len(_normalize_line_endings(tp.read_bytes()).splitlines()) if tp else 0
                except (OSError, UnicodeDecodeError):
                    added = 0

            content_for_classify = None
            if tp:
                try:
                    content_for_classify = tp.read_bytes()
                except OSError:
                    pass
            elif sp:
                try:
                    content_for_classify = sp.read_bytes()
                except OSError:
                    pass

            classification, reason = self._classify_file(path_str, content_for_classify)
            total_added += added
            total_removed += removed
            checksum_input.append(f"{change_type}:{path_str}:{added}:{removed}")

            changed_files.append(
                ChangedFileEntry(
                    file_path=path_str,
                    change_type=change_type,
                    classification=classification,
                    reason=reason,
                    lines_added=added,
                    lines_removed=removed,
                    is_binary=classification == ChangedFileClassification.BINARY,
                    is_generated=classification == ChangedFileClassification.GENERATED,
                    size_bytes=size_bytes,
                )
            )

        import hashlib

        diff_checksum = f"sha256:{hashlib.sha256('|'.join(checksum_input).encode()).hexdigest()}"
        files_by_class: dict[str, int] = {}
        for cf in changed_files:
            files_by_class[cf.classification.value] = files_by_class.get(cf.classification.value, 0) + 1

        return DiffSummary(
            total_files_changed=len(changed_files),
            total_lines_added=total_added,
            total_lines_removed=total_removed,
            files_by_classification=files_by_class,
            changed_files=changed_files,
            diff_checksum=diff_checksum,
        )

    def _compute_unified_diff(self, source_root: Path, target_root: Path, changed_files: list[ChangedFileEntry]) -> str:
        lines: list[str] = []
        for entry in changed_files:
            sp = source_root / entry.file_path
            tp = target_root / entry.file_path
            try:
                if entry.change_type == "deleted":
                    src_content = _normalize_line_endings(sp.read_bytes())
                    tgt_content = b""
                elif entry.change_type == "added":
                    src_content = b""
                    tgt_content = _normalize_line_endings(tp.read_bytes())
                else:
                    src_content = _normalize_line_endings(sp.read_bytes()) if sp.exists() else b""
                    tgt_content = _normalize_line_endings(tp.read_bytes()) if tp.exists() else b""
            except (OSError, UnicodeDecodeError):
                lines.append(f"diff --git a/{entry.file_path} b/{entry.file_path}")
                lines.append("Binary files differ")
                continue
            try:
                src_text = src_content.decode("utf-8", errors="replace").splitlines(keepends=True)
                tgt_text = tgt_content.decode("utf-8", errors="replace").splitlines(keepends=True)
            except Exception:
                lines.append(f"diff --git a/{entry.file_path} b/{entry.file_path}")
                lines.append("Binary files differ")
                continue
            diff = list(difflib.unified_diff(
                src_text, tgt_text,
                fromfile=f"a/{entry.file_path}",
                tofile=f"b/{entry.file_path}",
                lineterm="\n",
            ))
            if diff:
                lines.extend(diff)
        return "\n".join(lines)

    def _classify_file(self, path: str, content: bytes | None = None) -> tuple[ChangedFileClassification, SensitiveChangeReason | None]:
        path_lower = path.lower()

        # Forbidden: CI/CD pipeline configs
        if any(
            ci in path_lower
            for ci in [
                ".github/workflows/", ".github/actions/",
                ".gitlab-ci.yml", ".circleci/", "azure-pipelines",
                "jenkinsfile", "bitbucket-pipelines",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN, None

        # Forbidden: Credential and secret files
        if any(
            cred in path_lower
            for cred in [
                ".env", ".envrc",
                "credentials", "secrets",
                ".pem", ".key", ".cert", "id_rsa",
                "service-account", "kubeconfig",
                ".netrc", ".pgpass",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN, None

        # Forbidden: Security policy configs
        if any(
            sec in path_lower
            for sec in [
                "security", ".htaccess", ".htpasswd",
                "allowed_signers", "snyk", "codeql",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN, None

        if any(ext in path_lower for ext in [".bin", ".exe", ".dll", ".so", ".dylib", ".png", ".jpg", ".gif", ".ico"]):
            return ChangedFileClassification.BINARY, SensitiveChangeReason.BINARY_FILE
        if (
            path_lower.startswith("dist/")
            or path_lower.startswith("build/")
            or path_lower.startswith(".angular/")
            or path_lower.startswith("coverage/")
            or any(gen in path_lower for gen in ["/dist/", "/build/", "/.angular/", "node_modules", "/coverage/"])
        ):
            return ChangedFileClassification.GENERATED, SensitiveChangeReason.GENERATED_FILE
        if any(
            sens in path_lower
            for sens in ["auth", "security", "credential", "secret", "key", "token", "password"]
        ):
            classification = ChangedFileClassification.SENSITIVE
            reason = self._detect_content_reason(path, content) or SensitiveChangeReason.AUTH_OR_API
            return classification, reason
        if path_lower.endswith("package-lock.json") or path_lower.endswith("yarn.lock"):
            return ChangedFileClassification.MEDIUM_RISK, SensitiveChangeReason.PACKAGE_LOCK_CHANGE
        if path_lower.endswith(( ".ts", ".js", ".html", ".css", ".scss", ".json", ".py")):
            reason = self._detect_content_reason(path, content)
            return ChangedFileClassification.LOW_RISK, reason
        reason = self._detect_content_reason(path, content)
        return ChangedFileClassification.UNKNOWN, reason

    def _detect_content_reason(self, path: str, content: bytes | None = None) -> SensitiveChangeReason | None:
        if content is None:
            return None
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            return None
        if any(p in text for p in ["HttpClient", "HttpHeaders", "HttpParams", "HttpInterceptor", "HttpHandler", "HttpEvent", "HttpRequest", "HttpResponse"]):
            return SensitiveChangeReason.AUTH_OR_API
        if any(p in text for p in ["RouterModule", "RouterLink", "RouterOutlet", "CanActivate", "CanActivateChild", "CanDeactivate", "CanLoad", "CanMatch", "Route", "Router"]):
            return SensitiveChangeReason.AUTH_OR_API
        if any(p in text for p in ["localStorage", "sessionStorage", "document.cookie", "eval(", "Function(", "setTimeout(", "innerHTML", "outerHTML"]):
            return SensitiveChangeReason.SECURITY_RELEVANT
        if path == "angular.json" or path.endswith("/angular.json") or any(p in text for p in ['"builder"', '"architect"', '"schematics"']):
            return SensitiveChangeReason.BUILD_SYSTEM_CHANGE
        if path.endswith((".json", ".conf", ".config", ".ini", ".cfg", ".yaml", ".yml")) and not path.endswith(("package.json", "package-lock.json", "yarn.lock")):
            return SensitiveChangeReason.CONFIGURATION_CHANGE
        if any(p in text for p in ["ngOnChanges", "ngDoCheck", "ngAfterViewInit", "ngAfterContentInit", "ngAfterViewChecked", "ngAfterContentChecked"]):
            return SensitiveChangeReason.BEHAVIOR_CHANGE
        if any(p in text for p in ["@deprecated", "TODO.*migrat", "FIXME.*angular"]):
            return SensitiveChangeReason.HIDDEN_MODERNIZATION
        if any(p in text for p in ["FormsModule", "ReactiveFormsModule", "FormBuilder", "FormGroup", "FormControl", "FormArray", "Validators."]):
            return SensitiveChangeReason.FORM_THEME_CHANGE
        if path.endswith((".scss", ".sass", ".css")) and any(p in text.lower() for p in ["theme", "palette", "typography", "--primary", "--secondary", "--accent"]):
            return SensitiveChangeReason.FORM_THEME_CHANGE
        return None

    def _compute_package_changes(
        self, source_path: Path, target_path: Path
    ) -> PackageChangeSummary | None:
        """Compute package.json changes between source and target."""
        source_pkg = source_path / "package.json"
        target_pkg = target_path / "package.json"

        if not source_pkg.exists() or not target_pkg.exists():
            return None

        try:
            import json as _json

            sp = _json.loads(source_pkg.read_text())
            tp = _json.loads(target_pkg.read_text())
        except (OSError, _json.JSONDecodeError):
            return None

        def _diff_deps(a: dict, b: dict) -> tuple[list[str], list[str], list[dict[str, str]]]:
            a_deps = a or {}
            b_deps = b or {}
            added = [k for k in b_deps if k not in a_deps]
            removed = [k for k in a_deps if k not in b_deps]
            updated = [
                {"name": k, "from": a_deps[k], "to": b_deps[k]}
                for k in a_deps
                if k in b_deps and a_deps[k] != b_deps[k]
            ]
            return added, removed, updated

        deps_added, deps_removed, deps_updated = _diff_deps(
            sp.get("dependencies"), tp.get("dependencies")
        )
        dev_added, dev_removed, dev_updated = _diff_deps(
            sp.get("devDependencies"), tp.get("devDependencies")
        )

        ang_before = None
        ang_after = None
        all_deps = {**(sp.get("dependencies") or {}), **(sp.get("devDependencies") or {})}
        all_tdeps = {**(tp.get("dependencies") or {}), **(tp.get("devDependencies") or {})}
        for dep in ["@angular/core", "@angular/cli"]:
            if dep in all_deps:
                ang_before = all_deps[dep]
            if dep in all_tdeps:
                ang_after = all_tdeps[dep]

        other_major: list[str] = []
        for dep in deps_updated:
            from_major = _major(dep.get("from"))
            to_major = _major(dep.get("to"))
            if from_major is not None and to_major is not None and abs(to_major - from_major) >= 2:
                other_major.append(f"{dep['name']}: {dep['from']} -> {dep['to']} (major jump {from_major}->{to_major})")
        for dep in dev_updated:
            from_major = _major(dep.get("from"))
            to_major = _major(dep.get("to"))
            if from_major is not None and to_major is not None and abs(to_major - from_major) >= 2:
                other_major.append(f"{dep['name']}: {dep['from']} -> {dep['to']} (major jump {from_major}->{to_major})")

        return PackageChangeSummary(
            dependencies_added=deps_added,
            dependencies_removed=deps_removed,
            dependencies_updated=deps_updated,
            dev_dependencies_added=dev_added,
            dev_dependencies_removed=dev_removed,
            dev_dependencies_updated=dev_updated,
            angular_version_before=ang_before,
            angular_version_after=ang_after,
            other_major_changes=other_major,
        )

    def _scan_forbidden_changes(
        self, diff: DiffSummary, package: PackageChangeSummary | None
    ) -> list[ForbiddenChangeEntry]:
        forbidden: list[ForbiddenChangeEntry] = []
        for cf in diff.changed_files:
            if cf.classification == ChangedFileClassification.FORBIDDEN:
                forbidden.append(
                    ForbiddenChangeEntry(
                        file_path=cf.file_path,
                        reason="File is classified as forbidden for transformation",
                        risk_level=RiskLevel.CRITICAL,
                    )
                )
            if cf.classification == ChangedFileClassification.SENSITIVE:
                forbidden.append(
                    ForbiddenChangeEntry(
                        file_path=cf.file_path,
                        reason="Sensitive file change detected (auth/security/credentials)",
                        risk_level=RiskLevel.CRITICAL,
                        suggestion="Review manually before approving transformation",
                    )
                )
        if package and package.other_major_changes:
            for change in package.other_major_changes:
                forbidden.append(
                    ForbiddenChangeEntry(
                        file_path="package.json",
                        reason=f"Major package change: {change}",
                        risk_level=RiskLevel.MEDIUM,
                    )
                )
        return forbidden

    def _compute_overall_risk(self, diff: DiffSummary, forbidden: list[ForbiddenChangeEntry]) -> RiskLevel:
        if any(f.risk_level == RiskLevel.CRITICAL for f in forbidden):
            return RiskLevel.CRITICAL
        if any(f.risk_level == RiskLevel.HIGH for f in forbidden):
            return RiskLevel.HIGH
        if diff.total_files_changed > 100:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _dto(self, record, *, replay=False, source_sandbox_path=None, target_sandbox_path=None):
        from app.api.transformation_contracts import TransformationEvidenceResponse

        return TransformationEvidenceResponse(
            run_id=record.run_id,
            stage_id=record.stage_id,
            status=record.status,
            overall_risk_level=record.overall_risk_level,
            total_files_changed=record.total_files_changed,
            diff_checksum=record.diff_checksum,
            diff_summary=record.diff_summary,
            package_change=record.package_change_summary,
            migration_list=record.migration_list,
            forbidden_changes=record.forbidden_changes,
            changed_file_classifications=record.changed_file_classifications,
            evidence_complete=record.evidence_complete,
            artifact_ids=record.artifact_ids,
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            block_reason=record.block_reason,
            idempotent_replay=replay,
            correlation_id=record.correlation_id,
            source_sandbox_path=source_sandbox_path or record.source_sandbox_path,
            target_sandbox_path=target_sandbox_path or record.target_sandbox_path,
        )


# ── S3-F09 — G08 Approval Service ────────────────────────────────────────


class G08ApprovalApplicationService:
    GATE_ID = "G08"
    GATE_VERSION = "g08-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, stage_id: str, gate_id: str):
        if gate_id != self.GATE_ID:
            return None
        with self._scope() as session:
            record = session.scalar(
                select(G08ApprovalModel)
                .where(G08ApprovalModel.run_id == run_id)
                .where(G08ApprovalModel.stage_id == stage_id)
                .order_by(G08ApprovalModel.created_at.desc())
            )
            return self._dto(record) if record else None

    def initialize(self, run_id: str, stage_id: str, request) -> object:
        if request.gate_id != self.GATE_ID:
            raise G03ApplicationError("GATE_NOT_FOUND", "Only G08 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            existing = session.scalar(
                select(G08ApprovalModel)
                .where(G08ApprovalModel.run_id == run_id)
                .where(G08ApprovalModel.stage_id == stage_id)
                .order_by(G08ApprovalModel.created_at.desc())
            )
            if existing is not None:
                return self._dto(existing, replay=True)

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            record = self._create_pending_record(session, run, stage_id, request.actor, request.idempotency_key, now)
            return self._dto(record)

    def decide(self, run_id: str, stage_id: str, request) -> object:
        if request.gate_id != self.GATE_ID:
            raise G03ApplicationError("GATE_NOT_FOUND", "Only G08 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            existing_event = _find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(
                    select(G08ApprovalModel)
                    .where(G08ApprovalModel.run_id == run_id)
                    .order_by(G08ApprovalModel.created_at.desc())
                )
                if record is None:
                    raise G03ApplicationError("STALE_EVIDENCE", "G08 approval record not found.", status_code=409)
                return self._dto(record, replay=True)

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            record = session.scalar(
                select(G08ApprovalModel)
                .where(G08ApprovalModel.run_id == run_id)
                .where(G08ApprovalModel.stage_id == stage_id)
                .order_by(G08ApprovalModel.created_at.desc())
            )

            if record is None:
                record = self._create_pending_record(session, run, stage_id, request.actor, request.idempotency_key, now)

            # Build the package from stored evidence
            transformation_record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            evidence_record = session.scalar(
                select(TransformationEvidenceModel)
                .where(TransformationEvidenceModel.run_id == run_id)
                .where(TransformationEvidenceModel.stage_id == stage_id)
                .order_by(TransformationEvidenceModel.created_at.desc())
            )

            transform_result = AngularUpdateResult(
                run_id=run_id,
                stage_id=stage_id,
                update_status=AngularUpdateStatus(transformation_record.status) if transformation_record else AngularUpdateStatus.FAILED,
                target_version_status=TargetVersionStatus(transformation_record.target_version_status) if transformation_record else TargetVersionStatus.INCONCLUSIVE,
                resolved_target_version=transformation_record.resolved_target_version if transformation_record else None,
            )
            ev_result = TransformationEvidenceResult(
                run_id=run_id,
                stage_id=stage_id,
                diff=DiffSummary(total_files_changed=evidence_record.total_files_changed if evidence_record else 0, total_lines_added=0, total_lines_removed=0, diff_checksum=evidence_record.diff_checksum if evidence_record else "sha256:" + "0" * 64),
                evidence_complete=evidence_record.evidence_complete if evidence_record else False,
                overall_risk_level=RiskLevel(evidence_record.overall_risk_level) if evidence_record else RiskLevel.HIGH,
            )

            result: G08DecisionResult = G08ApprovalService().decide(
                G08EvidencePackage(
                    run_id=run_id,
                    stage_id=stage_id,
                    gate_version=self.GATE_VERSION,
                    state_version=run.state_version,
                    actor=request.actor,
                    transformation_result=transform_result,
                    evidence_result=ev_result,
                    artifact_set_checksum=record.artifact_set_checksum,
                    workspace_fingerprint=record.workspace_fingerprint,
                    package_checksum=record.package_checksum,
                ),
                request.decision,
                comment=request.comment,
            )

            event_type = self._decision_event_type(result.decision)
            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=event_type,
                    actor=request.actor,
                    reason=result.reason or f"G08 decision: {result.decision.value}",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={
                        "package_checksum": record.package_checksum,
                        "decision": result.decision.value,
                        "stage_id": stage_id,
                    },
                )
            )

            record.status = "stale" if result.stale else result.decision.value
            record.decision = result.decision.value
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            record.updated_at = now
            session.flush()
            return self._dto(record)

    def _create_pending_record(self, session, run, stage_id: str, actor: str, idempotency_key: str, now: datetime):
        """Create a pending G08 approval record with evidence package."""
        store = LocalFilesystemArtifactStore(
            Path(run.artifact_root), fixed_run_root=Path(run.artifact_root)
        ) if run.artifact_root else None

        # Collect artifact refs from transformation and evidence records
        transform_record = session.scalar(
            select(AngularUpdateRecordModel)
            .where(AngularUpdateRecordModel.run_id == run.id)
            .where(AngularUpdateRecordModel.stage_id == stage_id)
            .order_by(AngularUpdateRecordModel.created_at.desc())
        )
        evidence_record = session.scalar(
            select(TransformationEvidenceModel)
            .where(TransformationEvidenceModel.run_id == run.id)
            .where(TransformationEvidenceModel.stage_id == stage_id)
            .order_by(TransformationEvidenceModel.created_at.desc())
        )

        artifact_refs: list[ArtifactRefDto] = []
        artifact_ids: list[str] = []

        # Emit G08_CREATED event to get a real event sequence
        creation_transition = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id,
                expected_state_version=run.state_version,
                idempotency_key=f"{idempotency_key}:g08-created",
                event_type=WorkflowEventType.G08_CREATED,
                actor=actor,
                reason="G08 evidence package initialized",
                occurred_at=now,
                stage_id=stage_id,
                payload={"gate_version": self.GATE_VERSION, "stage_id": stage_id},
            ),
        )

        if store:
            # Build G08 evidence index artifact
            g08_payload = {
                "gate_version": self.GATE_VERSION,
                "transform_record_id": transform_record.id if transform_record else None,
                "evidence_record_id": evidence_record.id if evidence_record else None,
                "transform_artifact_ids": (transform_record.artifact_ids or []) if transform_record else [],
                "evidence_artifact_ids": (evidence_record.artifact_ids or []) if evidence_record else [],
            }
            ref = _write_evidence(
                store, session, run.id, f"g08_evidence_index_{stage_id}.json",
                g08_payload,
                stage_id=stage_id,
                created_by="g08-approval-service",
                created_at=now,
            )
            artifact_refs.append(ref)
            artifact_ids.append(ref.artifact_id)

        # Build the evidence package
        transform_result = AngularUpdateResult(
            run_id=run.id, stage_id=stage_id,
            update_status=AngularUpdateStatus(transform_record.status) if transform_record else AngularUpdateStatus.FAILED,
            target_version_status=TargetVersionStatus(transform_record.target_version_status) if transform_record else TargetVersionStatus.INCONCLUSIVE,
            resolved_target_version=transform_record.resolved_target_version if transform_record else None,
        )
        ev_result = TransformationEvidenceResult(
            run_id=run.id, stage_id=stage_id,
            diff=DiffSummary(
                total_files_changed=evidence_record.total_files_changed if evidence_record else 0,
                total_lines_added=0, total_lines_removed=0,
                diff_checksum=evidence_record.diff_checksum if evidence_record else "sha256:" + "0" * 64,
            ),
            evidence_complete=evidence_record.evidence_complete if evidence_record else False,
            overall_risk_level=RiskLevel(evidence_record.overall_risk_level) if evidence_record else RiskLevel.HIGH,
        )

        package = G08EvidencePackageBuilder().build(
            run_id=run.id, stage_id=stage_id,
            state_version=run.state_version, actor=actor,
            gate_version=self.GATE_VERSION,
            transformation_result=transform_result,
            evidence_result=ev_result,
            artifacts=artifact_refs,
            workspace_fingerprint=f"sha256:{uuid4().hex}",
        )

        record = G08ApprovalModel(
            id=f"g08-{uuid4().hex[:12]}",
            run_id=run.id,
            stage_id=stage_id,
            gate_id=self.GATE_ID,
            gate_version=package.gate_version,
            idempotency_key=idempotency_key,
            actor=actor,
            status="pending",
            package_checksum=package.package_checksum,
            artifact_set_checksum=package.artifact_set_checksum,
            workspace_fingerprint=package.workspace_fingerprint,
            state_version=creation_transition.next_state_version,
            event_sequence=creation_transition.event_sequence,
            package=package.model_dump(mode="json"),
            artifact_ids=artifact_ids,
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        session.flush()
        return record

    def _decision_event_type(self, decision: G08Decision) -> WorkflowEventType:
        mapping = {
            G08Decision.APPROVED: WorkflowEventType.G08_APPROVED,
            G08Decision.APPROVED_WITH_COMMENT: WorkflowEventType.G08_APPROVED,
            G08Decision.MODIFICATION_REQUESTED: WorkflowEventType.G08_MODIFICATION_REQUESTED,
            G08Decision.REJECTED: WorkflowEventType.G08_REJECTED,
        }
        return mapping.get(decision, WorkflowEventType.G08_REJECTED)

    def _dto(self, record, *, replay=False):
        from app.api.transformation_contracts import G08ReviewResponse

        return G08ReviewResponse(
            run_id=record.run_id,
            stage_id=record.stage_id,
            gate_id=record.gate_id,
            gate_version=record.gate_version,
            status=record.status,
            decision=record.decision,
            package=record.package,
            package_checksum=record.package_checksum,
            artifact_set_checksum=record.artifact_set_checksum,
            workspace_fingerprint=record.workspace_fingerprint,
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            idempotent_replay=replay,
            stale_reason=record.stale_reason,
            comment=record.comment,
        )
