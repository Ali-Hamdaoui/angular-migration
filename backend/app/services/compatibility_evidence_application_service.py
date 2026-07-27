"""Transactional persistence/API application service for S2-F05-I02."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app.api.compatibility_contracts import FeasibilityResponse, G05DecisionRequest, G05DecisionResponse
from app.artifact_store import ArtifactNotFoundError, LocalFilesystemArtifactStore
from app.domain.compatibility import CompatibilityCatalogue, CompatibilityResolutionRequest
from app.domain.contracts import ArtifactType, RunStatus, WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    CompatibilityCatalogueModel,
    CompatibilityResolutionModel,
    G05ApprovalModel,
    MigrationRunModel,
    PlanningJobModel,
    RegistrySnapshotModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.compatibility_application_service import (
    CompatibilityApplicationError,
    CompatibilityApplicationService,
    CompatibilityResolver,
)
from app.services.artifact_binding import canonical_artifact_references, canonical_artifact_set_checksum
from app.services.planning_job_service import PLANNING_JOB_NONTERMINAL_STATES, ensure_planning_job
from app.state.transition_service import StateTransitionService, StaleStateVersionError, TransitionError, TransitionRequest


class CompatibilityEvidenceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CompatibilityEvidenceApplicationService:
    GATE_VERSION = "g05-v1"
    G05_TTL = timedelta(hours=24)

    def __init__(self, *, session_scope_factory=session_scope, resolver: CompatibilityResolver, now_provider: Callable[[], datetime] | None = None, artifact_store_factory=None) -> None:
        self._scope = session_scope_factory
        self._resolver = resolver
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._artifact_store_factory = artifact_store_factory or self._store_for_run

    def resolve(self, run_id: str, payload, actor: str) -> FeasibilityResponse:
        now = self._now()
        with self._scope() as session:
            run = self._authorized_run(session, run_id, actor)
            try:
                request = self._request(run_id, payload, actor, now)
            except ValueError as error:
                raise CompatibilityEvidenceError("DOMAIN_VALIDATION_FAILED", "Feasibility input validation failed.", 422) from error
            policy = dict(run.run_policy_snapshot or {})
            policy.update({"source_angular_exact": request.source_angular_exact, "catalogue_version": request.catalogue_version, "registry_snapshot": {"snapshot_id": request.registry_snapshot_id, "checksum": request.registry_snapshot_checksum}, "runtime_candidates": [item.model_dump(mode="json") for item in request.runtime_candidates]})
            run.run_policy_snapshot = policy
            request_checksum = self._checksum({**payload.model_dump(mode="json"), "actor": actor})
            existing = session.scalar(select(CompatibilityResolutionModel).where(CompatibilityResolutionModel.run_id == run_id, CompatibilityResolutionModel.idempotency_key == payload.idempotency_key))
            if existing:
                if existing.request_checksum != request_checksum:
                    raise CompatibilityEvidenceError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", 409)
                return self._response(session, existing, replay=True)
            self._require_state(run, payload.expected_state_version)
            self._validate_prerequisites(session, run, request)
            try:
                result = CompatibilityApplicationService(resolver=self._resolver).resolve(request)
            except CompatibilityApplicationError as error:
                raise CompatibilityEvidenceError(error.code, error.message, error.status_code) from error
            except Exception as error:
                raise CompatibilityEvidenceError("COMPATIBILITY_RESOLUTION_FAILED", "Compatibility resolution failed closed.", 503) from error

            catalogue = self._resolver.catalogue
            catalogue_record = session.scalar(select(CompatibilityCatalogueModel).where(CompatibilityCatalogueModel.version == catalogue.version))
            if catalogue_record is None:
                session.add(CompatibilityCatalogueModel(id=f"catalogue-{uuid4().hex[:12]}", version=catalogue.version, checksum=catalogue.checksum, metadata_json=catalogue.model_dump(mode="json"), created_at=now))
            elif catalogue_record.checksum != catalogue.checksum:
                raise CompatibilityEvidenceError("CATALOGUE_CHECKSUM_MISMATCH", "The persisted catalogue checksum does not match the active catalogue.", 409)
            registry_record = session.scalar(select(RegistrySnapshotModel).where(RegistrySnapshotModel.run_id == run_id, RegistrySnapshotModel.snapshot_id == request.registry_snapshot_id))
            if registry_record is None:
                session.add(RegistrySnapshotModel(id=f"registry-{uuid4().hex[:12]}", run_id=run_id, snapshot_id=request.registry_snapshot_id, checksum=request.registry_snapshot_checksum, metadata_json={"snapshot_id": request.registry_snapshot_id, "candidate_count": len(request.runtime_candidates)}, created_at=now))
            elif registry_record.checksum != request.registry_snapshot_checksum:
                raise CompatibilityEvidenceError("REGISTRY_SNAPSHOT_CHECKSUM_MISMATCH", "The registry snapshot checksum does not match the persisted snapshot.", 409)
            artifact_ids, artifact_checksums = self._write_evidence(session, run, request, result, now)
            evidence_package_checksum = artifact_checksums[artifact_ids[-1]]
            started = self._transition(session, run, payload.idempotency_key + ":started", payload.expected_state_version, WorkflowEventType.COMPATIBILITY_RESOLUTION_STARTED, actor, now, {"catalogue_version": catalogue.version})
            final_type = WorkflowEventType.COMPATIBILITY_RESOLUTION_BLOCKED if result.status == "blocked" else WorkflowEventType.COMPATIBILITY_RESOLUTION_COMPLETED
            finished = self._transition(
                session,
                run,
                payload.idempotency_key,
                started.next_state_version,
                final_type,
                actor,
                now,
                {"status": result.status, "artifact_ids": artifact_ids},
                next_run_status=RunStatus.WAITING_PLAN_APPROVAL if result.status != "blocked" else None,
                next_run_phase="FEASIBILITY_PLANNING" if result.status != "blocked" else None,
                next_phase_status="waiting_approval" if result.status != "blocked" else None,
                next_approval_status="pending" if result.status != "blocked" else None,
            )
            gate_expires_at = now + self.G05_TTL
            gate_created = StateTransitionService(session).append_audit_event(run_id=run.id, idempotency_key=payload.idempotency_key + ":g05-created", event_type=WorkflowEventType.G05_CREATED, actor=actor, reason="G05 created", occurred_at=now, payload={"package_checksum": evidence_package_checksum, "expires_at": gate_expires_at.isoformat()})
            resolution = CompatibilityResolutionModel(
                id=f"compatibility-{uuid4().hex[:12]}", run_id=run_id, idempotency_key=payload.idempotency_key, request_checksum=request_checksum, actor=actor,
                status=result.status, catalogue_version=catalogue.version, catalogue_checksum=catalogue.checksum, registry_snapshot_id=request.registry_snapshot_id,
                registry_snapshot_checksum=request.registry_snapshot_checksum, source_exact=result.source_exact, source_family=result.source_family,
                target_family=result.target_family, support_level=result.support_level, route=[item.model_dump(mode="json") for item in result.route],
                 selected_profile=result.selected_profile.model_dump(mode="json") if result.selected_profile else None, blockers=list(result.package.blockers), warnings=list(result.package.warnings),
                 source_execution_profile_checksum=(result.selected_profile.source_execution_profile_checksum if result.selected_profile else None),
                 stage1_profile_checksum=(result.selected_profile.stage1_profile_checksum if result.selected_profile else None),
                package=result.package.model_dump(mode="json"), package_checksum=evidence_package_checksum, artifact_set_checksum=result.package.artifact_set_checksum,
                artifact_ids=artifact_ids, artifact_checksums=artifact_checksums, workspace_fingerprint=request.workspace_fingerprint, plan_version=request.plan_version,
                registry_snapshot={"snapshot_id": request.registry_snapshot_id, "checksum": request.registry_snapshot_checksum, "candidate_count": len(request.runtime_candidates)},
                runtime_candidates=[item.model_dump(mode="json") for item in request.runtime_candidates],
                state_version=gate_created.next_state_version, event_sequence=gate_created.event_sequence, created_at=now, updated_at=now,
                expires_at=gate_expires_at,
            )
            session.add(resolution)
            session.add(G05ApprovalModel(id=f"g05-{uuid4().hex[:12]}", run_id=run_id, gate_id="G05", gate_version=self.GATE_VERSION, idempotency_key="gate:" + payload.idempotency_key, actor=actor, status="blocked" if result.status == "blocked" else "pending", decision=None, package_checksum=evidence_package_checksum, artifact_set_checksum=result.package.artifact_set_checksum, workspace_fingerprint=request.workspace_fingerprint, plan_version=request.plan_version, state_version=gate_created.next_state_version, event_sequence=gate_created.event_sequence, artifact_ids=artifact_ids, prerequisite_artifact_ids=[item.artifact_id for item in request.prerequisite_artifacts], prerequisite_artifact_checksums={item.artifact_id: item.checksum for item in request.prerequisite_artifacts}, input_bundle_checksum=self._input_bundle_checksum(request.prerequisite_artifacts, evidence_package_checksum, request.workspace_fingerprint, request.plan_version), comment=None, stale_reason=None, expires_at=gate_expires_at, created_at=now, updated_at=now))
            session.flush()
            return self._response(session, resolution)

    def get(self, run_id: str, actor: str) -> FeasibilityResponse | None:
        with self._scope() as session:
            self._authorized_run(session, run_id, actor)
            resolution = session.scalar(select(CompatibilityResolutionModel).where(CompatibilityResolutionModel.run_id == run_id).order_by(CompatibilityResolutionModel.state_version.desc(), CompatibilityResolutionModel.created_at.desc()))
            return self._response(session, resolution) if resolution else None

    def decide_g05(self, run_id: str, payload: G05DecisionRequest, actor: str) -> G05DecisionResponse:
        now = self._now()
        request_checksum = self._checksum({**payload.model_dump(mode="json"), "run_id": run_id, "actor": actor})
        with self._scope() as session:
            run = self._authorized_run(session, run_id, actor)
            existing = session.scalar(select(G05ApprovalModel).where(G05ApprovalModel.run_id == run_id, G05ApprovalModel.idempotency_key == payload.idempotency_key))
            if existing:
                if (existing.request_checksum and existing.request_checksum != request_checksum) or existing.package_checksum != payload.package_checksum or existing.artifact_set_checksum != payload.artifact_set_checksum:
                    raise CompatibilityEvidenceError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", 409)
                return self._decision_response(existing, replay=True)
            self._require_state(run, payload.expected_state_version)
            gate = session.scalar(select(G05ApprovalModel).where(G05ApprovalModel.run_id == run_id, G05ApprovalModel.gate_id == "G05").order_by(G05ApprovalModel.state_version.desc(), G05ApprovalModel.created_at.desc()))
            if gate is None:
                raise CompatibilityEvidenceError("G05_NOT_FOUND", "Resolve feasibility before deciding G05.", 404)
            if gate.status == "blocked":
                raise CompatibilityEvidenceError("G05_BLOCKED", "Blocked feasibility cannot be approved.", 409)
            if payload.decision == "approve_with_comment" and not payload.comment or payload.comment is not None and not payload.comment.strip():
                raise CompatibilityEvidenceError("G05_COMMENT_REQUIRED", "An approval with comment requires a non-empty comment.", 422)
            if gate.expires_at is not None and self._as_utc(gate.expires_at) <= now:
                self._mark_g05_stale(session, run, gate, actor, now, "G05 approval package expired")
                session.commit()
                raise CompatibilityEvidenceError("G05_EXPIRED", "The G05 approval package has expired and must be regenerated.", 409)
            if payload.gate_version != gate.gate_version or payload.package_checksum != gate.package_checksum or payload.artifact_set_checksum != gate.artifact_set_checksum:
                self._mark_g05_stale(session, run, gate, actor, now, "G05 package binding changed")
                session.commit()
                raise CompatibilityEvidenceError("STALE_G05_BINDING", "The G05 package or binding is stale.", 409)
            if payload.workspace_fingerprint != gate.workspace_fingerprint or payload.plan_version != gate.plan_version:
                self._mark_g05_stale(session, run, gate, actor, now, "G05 workspace or plan binding changed")
                session.commit()
                raise CompatibilityEvidenceError("STALE_G05_BINDING", "The G05 workspace or plan binding is stale.", 409)
            self._verify_package(session, run, gate)
            event_type = {"approve": WorkflowEventType.G05_APPROVED, "approve_with_comment": WorkflowEventType.G05_APPROVED, "request_modification": WorkflowEventType.G05_MODIFICATION_REQUESTED, "reject": WorkflowEventType.G05_REJECTED}[payload.decision]
            transition = self._transition(
                session,
                run,
                payload.idempotency_key,
                payload.expected_state_version,
                event_type,
                actor,
                now,
                {"decision": payload.decision, "package_checksum": payload.package_checksum},
                next_run_status=RunStatus.PLANNING_RUNNING if payload.decision in {"approve", "approve_with_comment"} else RunStatus.WAITING_PLAN_APPROVAL,
                next_run_phase="FEASIBILITY_PLANNING",
                next_phase_status="running" if payload.decision in {"approve", "approve_with_comment"} else "waiting_approval",
                next_approval_status="approved" if payload.decision in {"approve", "approve_with_comment"} else "pending",
            )
            decision = G05ApprovalModel(id=f"g05-{uuid4().hex[:12]}", run_id=run_id, gate_id="G05", gate_version=gate.gate_version, idempotency_key=payload.idempotency_key, request_checksum=request_checksum, actor=actor, status="approved" if payload.decision in {"approve", "approve_with_comment"} else payload.decision, decision=payload.decision, package_checksum=gate.package_checksum, artifact_set_checksum=gate.artifact_set_checksum, workspace_fingerprint=gate.workspace_fingerprint, plan_version=gate.plan_version, state_version=transition.next_state_version, event_sequence=transition.event_sequence, artifact_ids=gate.artifact_ids, prerequisite_artifact_ids=list(gate.prerequisite_artifact_ids or []), prerequisite_artifact_checksums=dict(gate.prerequisite_artifact_checksums or {}), input_bundle_checksum=gate.input_bundle_checksum, comment=payload.comment.strip() if payload.comment else None, stale_reason=None, expires_at=gate.expires_at, created_at=now, updated_at=now)
            session.add(decision)
            if payload.decision in {"approve", "approve_with_comment"}:
                job = session.scalar(select(PlanningJobModel).where(PlanningJobModel.run_id == run_id, PlanningJobModel.status.in_(PLANNING_JOB_NONTERMINAL_STATES)).order_by(PlanningJobModel.created_at.desc()))
                if job is None:
                    job = ensure_planning_job(session, run, actor, gate.package_checksum, now, idempotency_key=f"planning-after-g05:{run_id}:{gate.package_checksum}")
                job.status = "generating_plan"
                job.current_step = "generating_plan"
                job.state_version = transition.next_state_version
                job.next_attempt_at = None
                job.last_error_code = job.last_error_message = job.last_error_stage = None
                job.retryable = False
                job.lease_expires_at = None
                job.worker_id = None
                job.updated_at = now
            session.flush()
            return self._decision_response(decision)

    def require_approved_g05(self, run_id: str, *, expected_state_version: int, workspace_fingerprint: str | None, plan_version: str | None, actor: str) -> G05ApprovalModel:
        with self._scope() as session:
            run = self._authorized_run(session, run_id, actor)
            self._require_state(run, expected_state_version)
            gate = session.scalar(select(G05ApprovalModel).where(G05ApprovalModel.run_id == run_id, G05ApprovalModel.gate_id == "G05").order_by(G05ApprovalModel.state_version.desc(), G05ApprovalModel.created_at.desc()))
            if gate is None or gate.status != "approved":
                raise CompatibilityEvidenceError("G05_APPROVAL_REQUIRED", "An approved current G05 gate is required before protected progression.", 409)
            current = self._now()
            if gate.expires_at is not None and self._as_utc(gate.expires_at) <= current:
                self._mark_g05_stale(session, run, gate, actor, current, "G05 approval package expired")
                session.commit()
                raise CompatibilityEvidenceError("G05_EXPIRED", "The approved G05 package has expired.", 409)
            if gate.workspace_fingerprint != workspace_fingerprint or gate.plan_version != plan_version:
                raise CompatibilityEvidenceError("G05_STALE", "The approved G05 bindings no longer match protected progression.", 409)
            self._verify_package(session, run, gate)
            return gate

    def _request(self, run_id, payload, actor, now):
        references = canonical_artifact_references(payload.prerequisite_artifacts)
        return CompatibilityResolutionRequest(run_id=run_id, expected_state_version=payload.expected_state_version, idempotency_key=payload.idempotency_key, actor=actor, source_angular_exact=payload.source_angular_exact, catalogue_version=payload.catalogue_version, registry_snapshot_id=payload.registry_snapshot_id, registry_snapshot_checksum=payload.registry_snapshot_checksum, prerequisite_artifacts=tuple(references), runtime_candidates=payload.runtime_candidates, workspace_topology=payload.workspace_topology, dependency_findings=payload.dependency_findings, source_execution_profile_checksum=getattr(payload, "source_execution_profile_checksum", None), workspace_fingerprint=payload.workspace_fingerprint, plan_version=payload.plan_version, resolved_at=payload.resolved_at or now)

    def _write_evidence(self, session, run, request, result, now):
        store = self._artifact_store_factory(run)
        contents = {
            "catalogue_snapshot": {"version": self._resolver.catalogue.version, "checksum": self._resolver.catalogue.checksum},
            "route": [item.model_dump(mode="json") for item in result.route],
            "support_level": {"support_level": result.support_level, "warnings": list(result.package.warnings), "blockers": list(result.package.blockers)},
            "registry_snapshot": {"snapshot_id": request.registry_snapshot_id, "checksum": request.registry_snapshot_checksum},
            "stage1_profile": result.selected_profile.model_dump(mode="json") if result.selected_profile else {"status": "unresolved"},
            "feasibility_package": result.package.model_dump(mode="json"),
        }
        ids, checksums = [], {}
        for name, value in contents.items():
            stored = store.write_text_artifact(run.id, f"04_workflow_state/feasibility/{name}.json", json.dumps(value, sort_keys=True, indent=2), ArtifactType.JSON, created_by="compatibility-evidence", created_at=now, policy_version="s2-f05-i02")
            ids.append(stored.ref.artifact_id)
            checksums[stored.ref.artifact_id] = stored.ref.checksum
            session.add(ArtifactMetadataModel(id="metadata-" + stored.ref.artifact_id, run_id=run.id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))
        return ids, checksums

    def _validate_prerequisites(self, session, run, request):
        for artifact in request.prerequisite_artifacts:
            row = session.get(ArtifactMetadataModel, "metadata-" + artifact.artifact_id)
            if row is None or row.run_id != run.id or row.checksum != artifact.checksum:
                raise CompatibilityEvidenceError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite artifact is missing or its checksum does not match.", 409)

    def _verify_package(self, session, run, gate):
        try:
            store = self._artifact_store_factory(run)
            if not gate.artifact_ids:
                raise CompatibilityEvidenceError("G05_PACKAGE_INTEGRITY_FAILED", "The G05 evidence set is empty.", 409)
            for artifact_id in gate.artifact_ids:
                metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
                stored = store.read_artifact_by_id(artifact_id)
                content_checksum = "sha256:" + hashlib.sha256(stored.content.encode("utf-8")).hexdigest()
                if metadata is None or metadata.run_id != run.id or metadata.checksum != stored.ref.checksum or content_checksum != stored.ref.checksum:
                    raise CompatibilityEvidenceError("G05_PACKAGE_INTEGRITY_FAILED", "A G05 evidence artifact checksum no longer matches its registered content.", 409)
            if store.read_artifact_by_id(gate.artifact_ids[-1]).ref.checksum != gate.package_checksum:
                raise CompatibilityEvidenceError("G05_PACKAGE_INTEGRITY_FAILED", "The G05 package checksum no longer matches stored evidence.", 409)
            references = canonical_artifact_references(
                {"artifact_id": artifact_id, "checksum": (gate.prerequisite_artifact_checksums or {}).get(artifact_id)}
                for artifact_id in (gate.prerequisite_artifact_ids or [])
            )
            if not references:
                raise CompatibilityEvidenceError("G05_INPUT_BUNDLE_MISSING", "The approved G05 input bundle is empty.", 409)
            if canonical_artifact_set_checksum(references) != gate.artifact_set_checksum:
                raise CompatibilityEvidenceError("G05_ARTIFACT_SET_CHECKSUM_MISMATCH", "The approved G05 artifact set checksum is stale.", 409)
            if gate.input_bundle_checksum != self._input_bundle_checksum(references, gate.package_checksum, gate.workspace_fingerprint, gate.plan_version):
                raise CompatibilityEvidenceError("G05_INPUT_BUNDLE_STALE", "The approved G05 input bundle checksum is stale.", 409)
        except CompatibilityEvidenceError:
            raise
        except (ArtifactNotFoundError, OSError, ValueError) as error:
            raise CompatibilityEvidenceError("G05_PACKAGE_INTEGRITY_FAILED", "The G05 package evidence is unavailable or invalid.", 409) from error

    def _mark_g05_stale(self, session, run, gate, actor, now, reason):
        transition = self._transition(session, run, "stale:" + gate.id, run.state_version, WorkflowEventType.G05_STALE, actor, now, {"reason": reason, "gate_version": gate.gate_version})
        gate.status = "stale"
        gate.stale_reason = reason
        gate.state_version = transition.next_state_version
        gate.event_sequence = transition.event_sequence
        gate.updated_at = now

    def reconcile_orphans(self, run_id: str, actor: str) -> dict[str, list[str]]:
        """Reconcile store sidecars and DB metadata without trusting either side alone."""
        with self._scope() as session:
            run = self._authorized_run(session, run_id, actor)
            store = self._artifact_store_factory(run)
            filesystem = {item.artifact_id for item in store.list_artifacts(run_id)}
            registered = {row.id.removeprefix("metadata-") for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id)).all()}
            missing_metadata = sorted(filesystem - registered)
            missing_files = sorted(registered - filesystem)
            checksum_mismatches = []
            for artifact_id in sorted(filesystem & registered):
                row = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
                stored = store.read_artifact_by_id(artifact_id)
                if row is None or row.checksum != stored.ref.checksum or "sha256:" + hashlib.sha256(stored.content.encode()).hexdigest() != stored.ref.checksum:
                    checksum_mismatches.append(artifact_id)
            return {"filesystem_orphans": missing_metadata, "database_orphans": missing_files, "checksum_mismatches": checksum_mismatches}

    def _transition(self, session, run, key, expected, event_type, actor, now, payload, **state_changes):
        try:
            return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=expected, idempotency_key=key, event_type=event_type, actor=actor, reason=event_type.value.lower(), occurred_at=now, payload=payload, **state_changes))
        except StaleStateVersionError as error:
            raise CompatibilityEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409) from error
        except TransitionError as error:
            raise CompatibilityEvidenceError("ILLEGAL_STATE_TRANSITION", "The requested workflow transition is not legal.", 409) from error

    def _authorized_run(self, session, run_id, actor):
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise CompatibilityEvidenceError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.actor and run.actor != actor:
            raise CompatibilityEvidenceError("RUN_NOT_AUTHORIZED", "Authenticated actor is not authorized for this run.", 403)
        return run

    @staticmethod
    def _require_state(run, expected):
        if run.state_version != expected:
            raise CompatibilityEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    def _response(self, session, row, replay=False):
        gate = session.scalar(select(G05ApprovalModel).where(G05ApprovalModel.run_id == row.run_id).order_by(G05ApprovalModel.state_version.desc(), G05ApprovalModel.created_at.desc()))
        return FeasibilityResponse(run_id=row.run_id, resolution_id=row.id, status=row.status, source_exact=row.source_exact, source_family=row.source_family, target_family=row.target_family, support_level=row.support_level, catalogue_snapshot={"version": row.catalogue_version, "checksum": row.catalogue_checksum}, registry_snapshot=row.registry_snapshot or {"snapshot_id": row.registry_snapshot_id, "checksum": row.registry_snapshot_checksum}, runtime_candidates=row.runtime_candidates or [], route=row.route, selected_profile=row.selected_profile, blockers=row.blockers, warnings=row.warnings, package=row.package, package_checksum=row.package_checksum, artifact_ids=row.artifact_ids, artifact_checksums=row.artifact_checksums, artifact_links={item: f"/api/v1/artifacts/{item}" for item in row.artifact_ids}, gate_version=gate.gate_version if gate else self.GATE_VERSION, gate_status=gate.status if gate else "blocked", gate_decision=gate.decision if gate else None, gate_created_at=gate.created_at if gate else None, gate_expires_at=gate.expires_at if gate else None, state_version=row.state_version, event_sequence=row.event_sequence, idempotent_replay=replay)

    @staticmethod
    def _decision_response(row, replay=False):
        return G05DecisionResponse(run_id=row.run_id, gate_version=row.gate_version, decision=row.decision or "pending", status=row.status, accepted=row.status == "approved", package_checksum=row.package_checksum, artifact_set_checksum=row.artifact_set_checksum, state_version=row.state_version, event_sequence=row.event_sequence, idempotent_replay=replay)

    @staticmethod
    def _checksum(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _input_bundle_checksum(artifacts, package_checksum, workspace_fingerprint, plan_version):
        references = canonical_artifact_references(artifacts)
        payload = {
            "artifacts": [[item["artifact_id"], item["checksum"]] for item in references],
            "package_checksum": package_checksum,
            "workspace_fingerprint": workspace_fingerprint,
            "plan_version": plan_version,
        }
        return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _store_for_run(run):
        root = Path(run.artifact_root)
        return LocalFilesystemArtifactStore(root, fixed_run_root=root)
