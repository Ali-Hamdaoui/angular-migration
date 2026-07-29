"""Transactional persistence/API service for S2-F06-I02."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import hashlib
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.planning_contracts import PlanCreateRequest, PlanResponse
from app.artifact_store import ArtifactNotFoundError, LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.domain.planning import PlanArtifactInput, PlanGenerationRequest
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    BuildSystemDecisionModel,
    CompatibilityResolutionModel,
    G05ApprovalModel,
    ExecutionProfileModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    StageExecutionPlanModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.domain.compatibility import calculate_stage1_profile_checksum
from app.services.planning_application_service import PlanningApplicationError, PlanningApplicationService
from app.services.artifact_binding import canonical_artifact_references, canonical_artifact_set_checksum
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceApplicationService
from app.state.transition_service import StateTransitionService, StaleStateVersionError, TransitionError, TransitionRequest


class PlanningEvidenceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class PlanningEvidenceApplicationService:
    """Persist plans only after Artifact Store finalization and semantic validation."""

    def __init__(self, *, scope=session_scope, now_provider=None, artifact_store_factory=None) -> None:
        self._scope = scope
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._artifact_store_factory = artifact_store_factory or self._store_for_run

    def record_failure(self, session, run, job, *, disposition, stage: str, diagnostic=None) -> tuple[str, object]:
        """Persist diagnostic evidence before exposing a planning failure."""
        now = self._now()
        details = {
            "run_id": run.id,
            "planning_job_id": job.id,
            "stage": stage,
            "attempt": job.attempt,
            "code": disposition.code,
            "retryable": disposition.retryable and not disposition.terminal,
            "logical_file": getattr(diagnostic, "logical_name", None),
            "resolved_path": str(getattr(diagnostic, "path", "")) if getattr(diagnostic, "path", None) else None,
            "file_checksum": getattr(diagnostic, "checksum", None),
            "encoding": getattr(diagnostic, "encoding", None),
            "bom_detected": getattr(diagnostic, "bom_detected", None),
            "parser_mode": getattr(diagnostic, "parser_mode", None),
            "exception_type": getattr(diagnostic, "exception_type", None),
            "line": getattr(diagnostic, "line", None),
            "column": getattr(diagnostic, "column", None),
            "position": getattr(diagnostic, "position", None),
            "expected_workspace_fingerprint": getattr(diagnostic, "expected_fingerprint", getattr(diagnostic, "expected_workspace_fingerprint", None)),
            "actual_workspace_fingerprint": getattr(diagnostic, "actual_fingerprint", None),
            "correlation_id": job.correlation_id,
            "occurred_at": now.isoformat(),
        }
        store = self._store_for_run(run)
        failure_names = {
            "resolving_feasibility": "planning-input-resolution-failure.json",
            "generating_plan": "planning-generation-failure.json",
            "running_planning_review": "planning-review-failure.json",
        }
        failure_name = failure_names.get(stage, "planning-failure.json")
        stored = store.write_text_artifact(run.id, f"03_planning/{failure_name}", json.dumps(details, sort_keys=True, indent=2), ArtifactType.JSON, created_by="planning-evidence", created_at=now, input_hashes={"planning_job": job.id, "attempt": str(job.attempt)}, policy_version="s2-f06-planning-failure-v2")
        session.add(ArtifactMetadataModel(id="metadata-" + stored.ref.artifact_id, run_id=run.id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now, finalized_at=now, immutable=True, correlation_id=job.correlation_id, safe_metadata=details))
        session.flush()
        return stored.ref.artifact_id, details

    def create(self, run_id: str, payload: PlanCreateRequest, actor: str) -> PlanResponse:
        now = self._now()
        with self._scope() as session:
            run = self._authorized_run(session, run_id, actor)
            try:
                request = self._request(run_id, payload, actor)
            except ValidationError as error:
                raise PlanningEvidenceError("DOMAIN_VALIDATION_FAILED", "Planning input validation failed.", 422) from error
            request_checksum = self._checksum(request.model_dump(mode="json"))
            existing = session.scalar(select(MigrationPlanModel).where(MigrationPlanModel.run_id == run_id, MigrationPlanModel.idempotency_key == payload.idempotency_key))
            if existing:
                if existing.request_checksum != request_checksum:
                    raise PlanningEvidenceError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", 409)
                return self._response(session, existing, replay=True)
            self._require_state(run, payload.expected_state_version)
            bound_artifacts, execution_profile_checksum = self._require_approved_feasibility(session, run, request)
            request = request.model_copy(
                update={
                    "prerequisite_artifacts": tuple(bound_artifacts),
                    "input_fingerprint": self._approved_artifact_set_checksum(bound_artifacts),
                    "execution_profile_checksum": execution_profile_checksum,
                }
            )
            self._validate_prerequisites(session, run, request)
            if session.scalar(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == "migration")) is not None:
                raise PlanningEvidenceError("ACTIVE_PLAN_EXISTS", "An active migration plan already exists; use its idempotent request or explicitly replace it.", 409)
            version = (session.scalar(select(func.max(MigrationPlanModel.version)).where(MigrationPlanModel.run_id == run_id)) or 0) + 1
            try:
                result = PlanningApplicationService(artifact_checksum_reader=lambda artifact_id: self._artifact_checksum(self._store_for_run(run), artifact_id)).generate(request, plan_version=version)
            except PlanningApplicationError as error:
                raise PlanningEvidenceError(error.code, error.message, error.status_code) from error
            except Exception as error:
                raise PlanningEvidenceError("PLAN_GENERATION_FAILED", "Plan generation failed closed.", 503) from error

            stage = result.first_stage_plan
            if stage is None:
                raise PlanningEvidenceError("STAGE_PLAN_MISSING", "Plan generation did not produce the first StageExecutionPlan.", 503)
            stage_parent = session.get(MigrationStageModel, stage.stage_id)
            if stage_parent is not None and stage_parent.run_id != run_id:
                raise PlanningEvidenceError(
                    "STAGE_ID_OWNERSHIP_CONFLICT",
                    "The planned stage identifier already belongs to another migration run.",
                    409,
                )
            if stage_parent is None:
                stage_parent = MigrationStageModel(
                    id=stage.stage_id,
                    run_id=run_id,
                    stage_order=session.query(MigrationStageModel).filter(MigrationStageModel.run_id == run_id).count() + 1,
                    source_version_family=stage.source_family,
                    target_version_family=stage.target_family,
                    source_version_detected=stage.source_exact,
                    target_version_resolved=stage.target_exact,
                    source_angular_version=stage.source_exact,
                    target_angular_version=stage.target_exact,
                    status="planned",
                    created_at=now,
                )
                session.add(stage_parent)
                session.flush()
            artifacts = self._write_artifacts(session, run, result, now)
            plan = MigrationPlanModel(id=result.plan.plan_id, run_id=run_id, idempotency_key=payload.idempotency_key, request_checksum=request_checksum, actor=actor, correlation_id=payload.correlation_id, status="generated", version=version, plan=result.plan.model_dump(mode="json"), checksum=result.plan.checksum, artifact_ids=artifacts[0], artifact_checksums=artifacts[1], state_version=run.state_version, event_sequence=0, created_at=now, updated_at=now)
            stage_record = StageExecutionPlanModel(id=stage.stage_plan_id, run_id=run_id, migration_plan_id=plan.id, stage_id=stage.stage_id, idempotency_key=payload.idempotency_key, request_checksum=request_checksum, actor=actor, correlation_id=payload.correlation_id, status="generated", version=version, stage_plan=stage.model_dump(mode="json"), checksum=stage.checksum, artifact_ids=artifacts[0], artifact_checksums=artifacts[1], state_version=run.state_version, event_sequence=0, created_at=now, updated_at=now)
            session.add_all([plan, stage_record])
            session.flush()
            decision = BuildSystemDecisionModel(id=f"decision-{uuid4().hex[:12]}", run_id=run_id, stage_plan_id=stage_record.id, decision_id=stage.build_system_decision.decision_id, decision=stage.build_system_decision.model_dump(mode="json"), checksum=stage.build_system_decision.checksum, created_at=now)
            session.add(decision)
            migration_event = self._transition(session, run, payload.idempotency_key + ":migration", payload.expected_state_version, WorkflowEventType.MIGRATION_PLAN_CREATED, actor, now, {"plan_id": plan.id, "artifact_ids": artifacts[0]})
            stage_event = self._transition(session, run, payload.idempotency_key, migration_event.next_state_version, WorkflowEventType.STAGE_PLAN_CREATED, actor, now, {"stage_id": stage.stage_id, "stage_plan_id": stage_record.id, "artifact_ids": artifacts[0]})
            plan.state_version, plan.event_sequence = migration_event.next_state_version, migration_event.event_sequence
            stage_record.state_version, stage_record.event_sequence = stage_event.next_state_version, stage_event.event_sequence
            session.add(ActivePlanVersionModel(id=f"active-plan-{uuid4().hex[:12]}", run_id=run_id, scope="migration", migration_plan_id=plan.id, stage_plan_id=None, version=version, state_version=plan.state_version, updated_at=now))
            session.add(ActivePlanVersionModel(id=f"active-stage-{uuid4().hex[:12]}", run_id=run_id, scope=stage.stage_id, migration_plan_id=plan.id, stage_plan_id=stage_record.id, version=version, state_version=stage_record.state_version, updated_at=now))
            session.flush()
            return self._response(session, plan)

    def get_plan(self, run_id: str, actor: str) -> PlanResponse | None:
        with self._scope() as session:
            self._authorized_run(session, run_id, actor)
            active = session.scalar(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == "migration"))
            return self._response(session, session.get(MigrationPlanModel, active.migration_plan_id)) if active else None

    def get_stage_plan(self, run_id: str, stage_id: str, actor: str) -> PlanResponse | None:
        with self._scope() as session:
            self._authorized_run(session, run_id, actor)
            active = session.scalar(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == stage_id))
            return self._response(session, session.get(MigrationPlanModel, active.migration_plan_id)) if active else None

    def _response(self, session, plan: MigrationPlanModel | None, replay=False) -> PlanResponse:
        if plan is None:
            raise PlanningEvidenceError("PLAN_NOT_FOUND", "The migration plan was not found.", 404)
        stage = session.scalar(select(StageExecutionPlanModel).where(StageExecutionPlanModel.migration_plan_id == plan.id).order_by(StageExecutionPlanModel.version.desc()))
        if stage is None:
            raise PlanningEvidenceError("STAGE_PLAN_NOT_FOUND", "The first StageExecutionPlan was not found.", 404)
        self._verify_artifacts(session, plan.run_id, plan.artifact_ids, plan.artifact_checksums)
        return PlanResponse(run_id=plan.run_id, status=plan.status, plan=plan.plan, stage_plan=stage.stage_plan, plan_checksum=plan.checksum, stage_plan_checksum=stage.checksum, artifact_ids=plan.artifact_ids, artifact_checksums=plan.artifact_checksums, artifact_links={item: f"/api/v1/artifacts/{item}" for item in plan.artifact_ids}, builder_decision=stage.stage_plan["build_system_decision"], state_version=stage.state_version, event_sequence=stage.event_sequence, idempotent_replay=replay)

    def _write_artifacts(self, session, run, result, now):
        store = self._store_for_run(run)
        stage = result.first_stage_plan
        values = {
            "03_planning/migration-plan.json": (result.plan.model_dump(mode="json"), None),
            f"stages/{stage.stage_id}/stage-execution-plan.json": (stage.model_dump(mode="json"), stage.stage_id),
            f"stages/{stage.stage_id}/builder-decision.json": (stage.build_system_decision.model_dump(mode="json"), stage.stage_id),
            f"stages/{stage.stage_id}/command-manifest.json": ({key: [item.model_dump(mode="json") for item in refs] for key, refs in stage.commands.items()}, stage.stage_id),
            f"stages/{stage.stage_id}/validation-matrix.json": (stage.validation_policy.model_dump(mode="json"), stage.stage_id),
            f"stages/{stage.stage_id}/recovery-map.json": (stage.recovery_policy.model_dump(mode="json"), stage.stage_id),
            f"stages/{stage.stage_id}/forbidden-change-policy.json": (stage.forbidden_change_policy.model_dump(mode="json"), stage.stage_id),
        }
        ids, checksums = [], {}
        for path, (value, stage_id) in values.items():
            stored = store.write_text_artifact(run.id, path, json.dumps(value, sort_keys=True, indent=2), ArtifactType.JSON, stage_id=stage_id, created_by="planning-evidence", created_at=now, input_hashes={"plan": result.plan.checksum, "stage_plan": stage.checksum}, policy_version="s2-f06-i02")
            ids.append(stored.ref.artifact_id)
            checksums[stored.ref.artifact_id] = stored.ref.checksum
            session.add(ArtifactMetadataModel(id="metadata-" + stored.ref.artifact_id, run_id=run.id, stage_id=stage_id, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))
        return ids, checksums

    def _validate_prerequisites(self, session, run, request):
        store = self._store_for_run(run)
        for artifact in request.prerequisite_artifacts:
            row = session.get(ArtifactMetadataModel, "metadata-" + artifact.artifact_id)
            if row is None or row.run_id != run.id or row.checksum != artifact.checksum:
                raise PlanningEvidenceError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite artifact is missing or its checksum does not match.", 409)
            try:
                self._verify_stored(store, artifact.artifact_id, artifact.checksum)
            except (ArtifactNotFoundError, OSError, ValueError) as error:
                raise PlanningEvidenceError("PREREQUISITE_ARTIFACT_UNAVAILABLE", "A prerequisite artifact is unavailable.", 409) from error

    def _require_approved_feasibility(self, session, run, request):
        gate = session.scalar(select(G05ApprovalModel).where(G05ApprovalModel.run_id == run.id, G05ApprovalModel.gate_id == "G05", G05ApprovalModel.status == "approved").order_by(G05ApprovalModel.state_version.desc(), G05ApprovalModel.created_at.desc()))
        if gate is None:
            raise PlanningEvidenceError("G05_APPROVAL_REQUIRED", "An approved current G05 feasibility package is required before plan generation.", 409)
        resolution = session.scalar(select(CompatibilityResolutionModel).where(CompatibilityResolutionModel.run_id == run.id, CompatibilityResolutionModel.package_checksum == gate.package_checksum).order_by(CompatibilityResolutionModel.created_at.desc()))
        if resolution is None or resolution.package_checksum != gate.package_checksum or resolution.artifact_set_checksum != gate.artifact_set_checksum:
            raise PlanningEvidenceError("STALE_G05_BINDING", "The approved G05 feasibility package binding is stale.", 409)
        package = resolution.package
        if any((request.source_exact, request.source_family, request.target_family, request.catalogue_version)[i] != package.get(key) for i, key in enumerate(("source_exact", "source_family", "target_family", "catalogue_version"))):
            raise PlanningEvidenceError("FEASIBILITY_INPUT_MISMATCH", "Planning inputs do not match the approved feasibility package.", 409)
        profile = package.get("selected_profile") or {}
        if request.execution_profile_id != profile.get("profile_id"):
            raise PlanningEvidenceError("FEASIBILITY_INPUT_MISMATCH", "The planning execution profile does not match the approved Stage 1 profile.", 409)
        execution_profile = session.scalar(
            select(ExecutionProfileModel)
            .where(
                ExecutionProfileModel.run_id == run.id,
                ExecutionProfileModel.selected_profile_id == profile.get("profile_id"),
            )
            .order_by(ExecutionProfileModel.created_at.desc())
        )
        if execution_profile is None or execution_profile.status not in {"resolved", "selected"}:
            raise PlanningEvidenceError("PLANNING_RUNTIME_PROFILE_MISSING", "The selected execution profile is not durably resolved for this run.", 409)
        if not profile.get("source_execution_profile_checksum") or execution_profile.selected_checksum != profile.get("source_execution_profile_checksum"):
            raise PlanningEvidenceError("STALE_EXECUTION_PROFILE", "The selected execution profile checksum no longer matches the approved G05 binding.", 409)
        if calculate_stage1_profile_checksum(profile) != profile.get("stage1_profile_checksum") or profile.get("checksum") != profile.get("stage1_profile_checksum"):
            raise PlanningEvidenceError("STALE_EXECUTION_PROFILE", "The approved Stage 1 profile checksum is invalid.", 409)
        persisted_profile = next(
            (
                item
                for item in execution_profile.profiles
                if item.get("profile_id") == profile.get("profile_id")
                and item.get("checksum") == execution_profile.selected_checksum
            ),
            None,
        )
        if persisted_profile is None:
            raise PlanningEvidenceError("STALE_EXECUTION_PROFILE", "The approved execution profile record is incomplete or has drifted.", 409)
        approved_route = package.get("route") or []
        if len(request.stage_route) != len(approved_route):
            raise PlanningEvidenceError("FEASIBILITY_INPUT_MISMATCH", "The planning route does not match the approved feasibility route.", 409)
        for index, (supplied, approved) in enumerate(zip(request.stage_route, approved_route)):
            supplied_cli = request.target_cli_exact if index == 0 and request.target_cli_exact else (supplied[4] if len(supplied) == 5 else supplied[3])
            if tuple(supplied[:3]) != (approved.get("source_family"), approved.get("target_family"), approved.get("stage_id")) or supplied[3] != approved.get("target_angular_exact") or supplied_cli != approved.get("target_cli_exact"):
                raise PlanningEvidenceError("FEASIBILITY_INPUT_MISMATCH", "The planning route contains an exact target that differs from the approved feasibility package.", 409)
        approved_ids = list(gate.prerequisite_artifact_ids or gate.artifact_ids)
        approved_checksums = dict(gate.prerequisite_artifact_checksums or resolution.artifact_checksums or {})
        if not gate.input_bundle_checksum:
            raise PlanningEvidenceError("G05_INPUT_BUNDLE_MISSING", "The approved G05 input bundle is incomplete.", 409)
        if any(not approved_checksums.get(artifact_id) for artifact_id in approved_ids):
            raise PlanningEvidenceError("STALE_G05_BINDING", "The approved G05 artifact bundle is incomplete or tampered.", 409)
        bound = canonical_artifact_references(
            {"artifact_id": artifact_id, "checksum": approved_checksums.get(artifact_id)}
            for artifact_id in approved_ids
        )
        if canonical_artifact_set_checksum(bound) != gate.artifact_set_checksum:
            raise PlanningEvidenceError("G05_ARTIFACT_SET_CHECKSUM_MISMATCH", "The approved G05 artifact bundle is stale or tampered.", 409)
        expected_bundle = CompatibilityEvidenceApplicationService._input_bundle_checksum(
            bound, gate.package_checksum, gate.workspace_fingerprint, gate.plan_version
        )
        if gate.input_bundle_checksum != expected_bundle:
            raise PlanningEvidenceError("G05_INPUT_BUNDLE_STALE", "The approved G05 input bundle checksum is stale or tampered.", 409)
        return tuple(PlanArtifactInput(**item) for item in bound), execution_profile.selected_checksum

    @staticmethod
    def _approved_artifact_set_checksum(references):
        from app.services.artifact_binding import canonical_artifact_set_checksum

        return canonical_artifact_set_checksum(references)

    def _verify_artifacts(self, session, run_id, artifact_ids, checksums):
        run = session.get(MigrationRunModel, run_id)
        store = self._store_for_run(run)
        for artifact_id in artifact_ids:
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
            if metadata is None or metadata.run_id != run_id or checksums.get(artifact_id) != metadata.checksum:
                raise PlanningEvidenceError("PLAN_ARTIFACT_INTEGRITY_FAILED", "A registered plan artifact is missing or has changed.", 409)
            try:
                self._verify_stored(store, artifact_id, metadata.checksum)
            except (ArtifactNotFoundError, OSError, ValueError) as error:
                raise PlanningEvidenceError("PLAN_ARTIFACT_INTEGRITY_FAILED", "A registered plan artifact is missing or has changed.", 409) from error

    @staticmethod
    def _verify_stored(store, artifact_id, checksum):
        stored = store.read_artifact_by_id(artifact_id)
        actual = "sha256:" + hashlib.sha256(stored.content.encode("utf-8")).hexdigest()
        if stored.ref.checksum != checksum or actual != checksum:
            raise ValueError("artifact checksum mismatch")

    @staticmethod
    def _artifact_checksum(store, artifact_id):
        return store.read_artifact_by_id(artifact_id).ref.checksum

    def _transition(self, session, run, key, expected, event_type, actor, now, payload):
        try:
            return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=expected, idempotency_key=key, event_type=event_type, actor=actor, reason=event_type.value.lower(), occurred_at=now, payload=payload))
        except StaleStateVersionError as error:
            raise PlanningEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409) from error
        except TransitionError as error:
            raise PlanningEvidenceError("ILLEGAL_STATE_TRANSITION", "The requested workflow transition is not legal.", 409) from error

    def _authorized_run(self, session, run_id, actor):
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise PlanningEvidenceError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.actor and run.actor != actor:
            raise PlanningEvidenceError("RUN_NOT_AUTHORIZED", "Authenticated actor is not authorized for this run.", 403)
        return run

    @staticmethod
    def _require_state(run, expected):
        if run.state_version != expected:
            raise PlanningEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    @staticmethod
    def _request(run_id, payload, actor):
        return PlanGenerationRequest(run_id=run_id, actor=actor, **payload.model_dump(mode="json"))

    @staticmethod
    def _checksum(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _store_for_run(run):
        root = Path(run.artifact_root)
        return LocalFilesystemArtifactStore(root, fixed_run_root=root)
