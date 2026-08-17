"""Durable application service for S1-F10 baseline preparation."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.baseline import BaselinePrequalificationService, BaselinePrequalificationResult
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.repositories.baseline_models import BaselineQualificationModel
from app.repositories.models import ArtifactMetadataModel, ExecutionProfileModel, MigrationRunModel, SourceSnapshotModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest, StaleStateVersionError
from app.workspaces.baseline import BaselineSandboxRecord, BaselineSandboxService, baseline_tree_fingerprint


class BaselineApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class BaselineApplicationService:
    """Persist baseline evidence only after authoritative boundary checks."""

    def __init__(self, *, session_scope_factory=session_scope, g02_service=None, execution_profile_service=None, sandbox_service=None, prequalifier=None, now_provider=None):
        self._scope = session_scope_factory
        self._g02 = g02_service
        self._profiles = execution_profile_service
        self._sandbox = sandbox_service or BaselineSandboxService()
        self._prequalifier = prequalifier or BaselinePrequalificationService()
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str) -> object | None:
        with self._scope() as session:
            record = session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == run_id).order_by(BaselineQualificationModel.created_at.desc()))
            return self._response(record) if record else None

    def create_workspace(self, run_id: str, request) -> object:
        now = self._now()
        with self._scope() as session:
            run = self._run(session, run_id)
            existing = self._existing(session, run_id, request.idempotency_key)
            if existing:
                return self._response(existing, replay=True)
            self._require_state(run, request.expected_state_version)
            if self._g02 is None or not hasattr(self._g02, "authorize_baseline"):
                raise BaselineApplicationError("BASELINE_G02_REQUIRED", "Approved G02 evidence is required.", 409)
            try:
                package = self._g02.authorize_baseline(run_id)
            except Exception as error:
                raise BaselineApplicationError(getattr(error, "code", "BASELINE_G02_REQUIRED"), str(error), 409) from error
            if self._profiles is None or not hasattr(self._profiles, "validate_for_baseline"):
                raise BaselineApplicationError("EXECUTION_PROFILE_REQUIRED", "A selected execution profile is required.", 409)
            try:
                self._profiles.validate_for_baseline(run_id, expected_state_version=request.expected_state_version, idempotency_key=request.idempotency_key + ":profile", actor=request.actor)
            except Exception as error:
                raise BaselineApplicationError(getattr(error, "code", "EXECUTION_PROFILE_REQUIRED"), str(error), 409) from error
            self._transition(session, run, request, WorkflowEventType.BASELINE_WORKSPACE_STARTED, "baseline sandbox creation started", {"snapshot_id": package.snapshot_id})
            snapshot = session.get(SourceSnapshotModel, package.snapshot_id)
            if snapshot is None:
                raise BaselineApplicationError("SOURCE_SNAPSHOT_NOT_FOUND", "The approved source snapshot does not exist.", 409)
            if snapshot.run_id != run_id:
                raise BaselineApplicationError("SOURCE_SNAPSHOT_RUN_MISMATCH", "The approved source snapshot does not belong to this migration run.", 409)

            aliases = run.workspace_aliases or {}
            source_snapshot_raw = aliases.get("SOURCE_SNAPSHOT")
            baseline_raw = aliases.get("BASELINE_SANDBOX")
            if not isinstance(source_snapshot_raw, str) or not source_snapshot_raw.strip() or not isinstance(baseline_raw, str) or not baseline_raw.strip():
                raise BaselineApplicationError("BASELINE_LAYOUT_REQUIRED", "Registered source-snapshot and baseline aliases are required.", 409)
            try:
                source_snapshot_container = Path(source_snapshot_raw).resolve(strict=True)
                baseline_path = Path(baseline_raw)
                snapshot_root = Path(snapshot.snapshot_path).resolve(strict=True)
                run_root = Path(run.run_root).resolve(strict=True) if run.run_root else None
            except (OSError, TypeError) as error:
                raise BaselineApplicationError("BASELINE_WORKSPACE_FAILED", str(error), 422) from error
            try:
                snapshot_root.relative_to(source_snapshot_container)
                if run_root is not None:
                    snapshot_root.relative_to(run_root)
            except ValueError as error:
                raise BaselineApplicationError("BASELINE_LAYOUT_INVALID", "The approved snapshot must remain inside the registered workspace boundaries.", 422) from error
            existing_workspace = self._latest(session, run_id)
            if (
                existing_workspace is not None
                and Path(existing_workspace.sandbox_path).resolve() == baseline_path.resolve()
                and baseline_path.is_dir()
                and existing_workspace.input_fingerprint == package.snapshot_fingerprint
            ):
                try:
                    fingerprint = baseline_tree_fingerprint(baseline_path)
                except (OSError, ValueError, TypeError):
                    fingerprint = None
                if fingerprint == existing_workspace.sandbox_fingerprint:
                    workspace = BaselineSandboxRecord(
                        run_id=run_id,
                        sandbox_path=baseline_path.resolve(),
                        input_fingerprint=existing_workspace.input_fingerprint,
                        fingerprint=fingerprint,
                    )
                else:
                    workspace = None
            else:
                workspace = None
            try:
                if workspace is None:
                    workspace = self._sandbox.create(run_id=run_id, snapshot_root=snapshot_root, baseline_path=baseline_path, approved_snapshot_fingerprint=package.snapshot_fingerprint, registered_run_root=run_root)
            except (OSError, ValueError, TypeError) as error:
                raise BaselineApplicationError("BASELINE_WORKSPACE_FAILED", str(error), 422) from error
            artifacts = self._write_artifact(session, run, "baseline_workspace_manifest.json", {"run_id": run_id, "snapshot_id": package.snapshot_id, "input_fingerprint": workspace.input_fingerprint, "sandbox_fingerprint": workspace.fingerprint, "sandbox_path": str(workspace.sandbox_path), "excluded_paths": list(workspace.excluded_paths)}, request.idempotency_key, now)
            artifacts += self._write_artifact(session, run, "baseline_copy_report.json", {"status": "verified", "source_snapshot": str(snapshot_root), "baseline_sandbox": str(workspace.sandbox_path), "input_fingerprint": workspace.input_fingerprint, "sandbox_fingerprint": workspace.fingerprint, "excluded_paths": list(workspace.excluded_paths)}, request.idempotency_key, now)
            artifacts += self._write_artifact(session, run, "baseline_initial_fingerprint.json", {"status": "captured", "fingerprint": workspace.fingerprint, "source_snapshot_fingerprint": workspace.input_fingerprint}, request.idempotency_key, now)
            transition = self._transition(session, run, request, WorkflowEventType.BASELINE_WORKSPACE_READY, "baseline sandbox created", {"snapshot_id": package.snapshot_id, "sandbox_fingerprint": workspace.fingerprint, "artifact_count": len(artifacts)})
            record = BaselineQualificationModel(id=f"baseline-{uuid4().hex[:12]}", run_id=run_id, idempotency_key=request.idempotency_key, actor=request.actor, status="workspace_ready", snapshot_id=package.snapshot_id, sandbox_path=str(workspace.sandbox_path), input_fingerprint=workspace.input_fingerprint, sandbox_fingerprint=workspace.fingerprint, package=None, lockfile=None, sources=[], scripts=[], registry=None, blockers=[], warnings=[], authorization_status="not_authorized", checksum=workspace.fingerprint, artifact_ids=artifacts, state_version=transition.next_state_version, event_sequence=transition.event_sequence, created_at=now, updated_at=now)
            session.add(record)
            session.flush()
            return self._response(record)

    def prequalify(self, run_id: str, request) -> object:
        now = self._now()
        with self._scope() as session:
            run = self._run(session, run_id)
            existing = self._existing(session, run_id, request.idempotency_key)
            if existing and existing.status != "workspace_ready":
                return self._response(existing, replay=True)
            self._require_state(run, request.expected_state_version)
            record = self._latest(session, run_id)
            if record is None or record.status not in {"workspace_ready", "requires_review", "blocked", "qualified"}:
                raise BaselineApplicationError("BASELINE_WORKSPACE_REQUIRED", "Create the baseline workspace before prequalification.", 409)
            profile = self._selected_profile(session, run_id)
            result = self._prequalifier.qualify(Path(record.sandbox_path), execution_profile=profile, private_auth_configured=request.private_auth_configured)
            artifact_ids = list(record.artifact_ids or [])
            payloads = {"package_manager_detection.json": {"package": result.package, "lockfile": result.lockfile}, "npm_configuration_summary.json": result.registry, "lifecycle_script_risk_report.json": result.scripts, "baseline_preparation_result.json": {"status": result.status, "blockers": list(result.blockers), "warnings": list(result.warnings), "checksum": result.checksum}}
            for name, payload in payloads.items():
                artifact_ids.append(self._write_artifact(session, run, name, payload, request.idempotency_key, now)[0])
            transition = self._transition(session, run, request, WorkflowEventType.LOCKFILE_PREQUALIFICATION_COMPLETED, "baseline package prequalification completed", {"status": result.status, "checksum": result.checksum})
            if result.authorization_required:
                transition = self._transition(session, run, request, WorkflowEventType.LIFECYCLE_SCRIPT_REVIEW_REQUIRED, "lifecycle script review is required before install", {"script_count": len(result.scripts)})
            record.idempotency_key = request.idempotency_key
            record.status = result.status
            record.package = _jsonable(result.package)
            record.lockfile = _jsonable(result.lockfile)
            record.sources = _jsonable(result.sources)
            record.scripts = _jsonable(result.scripts)
            record.registry = _jsonable(result.registry)
            record.blockers = list(result.blockers)
            record.warnings = list(result.warnings)
            record.authorization_status = "review_required" if result.authorization_required else ("blocked" if result.blockers else "not_required")
            record.checksum = result.checksum
            record.artifact_ids = artifact_ids
            record.state_version, record.event_sequence, record.updated_at = transition.next_state_version, transition.event_sequence, now
            session.flush()
            return self._response(record)

    def authorize_install(self, run_id: str, request) -> object:
        now = self._now()
        with self._scope() as session:
            run = self._run(session, run_id)
            record = self._latest(session, run_id)
            if record is None or record.status not in {"requires_review", "qualified"}:
                raise BaselineApplicationError("BASELINE_PREQUALIFICATION_REQUIRED", "Prequalification must complete before authorization.", 409)
            self._require_state(run, request.expected_state_version)
            if request.decision == "authorize" and record.blockers:
                raise BaselineApplicationError("BASELINE_INSTALL_BLOCKED", "Blocked prequalification cannot be authorized.", 409)
            event_type = WorkflowEventType.BASELINE_INSTALL_AUTHORIZED if request.decision == "authorize" else WorkflowEventType.BASELINE_INSTALL_BLOCKED
            transition = self._transition(session, run, request, event_type, "baseline install authorization decided", {"decision": request.decision, "comment": request.comment})
            record.idempotency_key = request.idempotency_key
            record.authorization_status = "authorized" if request.decision == "authorize" else "rejected"
            record.state_version, record.event_sequence, record.updated_at = transition.next_state_version, transition.event_sequence, now
            session.flush()
            return self._response(record)

    def _write_artifact(self, session, run, name, payload, idempotency_key, now):
        root = Path(run.artifact_root or "").resolve()
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        store.ensure_run_layout(run.id)
        stored = store.write_text_artifact(run.id, f"01_baseline/{name}", json.dumps(_jsonable(payload), indent=2, sort_keys=True, default=str), ArtifactType.JSON, created_by="baseline-application-service", created_at=now, input_hashes={"request": idempotency_key}, policy_version="baseline-prequalification-v1")
        session.add(ArtifactMetadataModel(id=f"metadata-{stored.ref.artifact_id}", run_id=run.id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))
        return [stored.ref.artifact_id]

    @staticmethod
    def _json_response(record, replay=False):
        return record

    def _response(self, record, replay=False):
        from app.api.baseline_contracts import BaselineResponse
        return BaselineResponse(run_id=record.run_id, status=record.status, policy_version="baseline-prequalification-v1", snapshot_id=record.snapshot_id, sandbox_path=record.sandbox_path, input_fingerprint=record.input_fingerprint, sandbox_fingerprint=record.sandbox_fingerprint, package=record.package, lockfile=record.lockfile, sources=record.sources or [], scripts=record.scripts or [], registry=record.registry, blockers=record.blockers or [], warnings=record.warnings or [], authorization_status=record.authorization_status, checksum=record.checksum, artifact_ids=record.artifact_ids or [], state_version=record.state_version, event_sequence=record.event_sequence, idempotent_replay=replay)

    @staticmethod
    def _run(session, run_id):
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise BaselineApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        return run

    @staticmethod
    def _latest(session, run_id):
        return session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == run_id).order_by(BaselineQualificationModel.created_at.desc()))

    @staticmethod
    def _existing(session, run_id, key):
        return session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == run_id, BaselineQualificationModel.idempotency_key == key))

    @staticmethod
    def _require_state(run, expected):
        if run.state_version != expected:
            raise BaselineApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    @staticmethod
    def _selected_profile(session, run_id):
        record = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.created_at.desc()))
        if record is None or not record.selected_profile_id:
            return None
        from app.domain.execution_profile import ExecutionProfile
        selected = next((item for item in record.profiles if item.get("profile_id") == record.selected_profile_id and item.get("checksum") == record.selected_checksum), None)
        return ExecutionProfile.model_validate(selected) if selected else None

    @staticmethod
    def _transition(session, run, request, event_type, reason, payload):
        try:
            return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=run.state_version, idempotency_key=request.idempotency_key + (":started" if event_type is WorkflowEventType.BASELINE_WORKSPACE_STARTED else ":lifecycle-review" if event_type is WorkflowEventType.LIFECYCLE_SCRIPT_REVIEW_REQUIRED else ""), event_type=event_type, actor=request.actor, reason=reason, occurred_at=datetime.now(UTC), payload=payload))
        except StaleStateVersionError as error:
            raise BaselineApplicationError("STALE_STATE_VERSION", str(error), 409) from error


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if hasattr(value, "value"):
        return value.value
    return value
