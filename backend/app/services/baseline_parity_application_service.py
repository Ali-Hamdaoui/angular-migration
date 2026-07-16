"""Persistence and API application service for S1-F13 parity evidence."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.baseline_parity_contracts import BaselineParityResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.baseline_parity import (
    PARSER_VERSION,
    SCHEMA_VERSION,
    BackendContractSnapshotBuilder,
    BaselineFailureFingerprintService,
    EvidenceConfidence,
    RouteInventoryBuilder,
    anchor_to_dict,
)
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    BaselineParityEvidenceModel,
    BaselineQualificationModel,
    BaselineValidationModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    MigrationRunModel,
)
from app.repositories.session import session_scope
from app.state.transition_service import StaleStateVersionError, StateTransitionService, TransitionRequest


class BaselineParityApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class BaselineParityApplicationService:
    def __init__(self, *, scope=session_scope, now_provider=None):
        self._scope = scope
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._fingerprints = BaselineFailureFingerprintService()

    def capture(self, run_id: str, request) -> BaselineParityResponse:
        with self._scope() as session:
            run, baseline = self._run_and_baseline(session, run_id)
            replay = session.scalar(select(BaselineParityEvidenceModel).where(
                BaselineParityEvidenceModel.run_id == run_id,
                BaselineParityEvidenceModel.idempotency_key == request.idempotency_key,
            ))
            if replay:
                return self._response(replay, replay=True)
            self._require_state(run, request.expected_state_version)
            self._require_prerequisites(session, run, baseline, request.prerequisite_artifact_ids, request.prerequisite_artifact_checksums)
            validations = session.scalars(select(BaselineValidationModel).where(
                BaselineValidationModel.run_id == run_id,
            )).all()
            profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))
            run_root = Path(run.artifact_root).resolve()
            sandbox = Path(baseline.sandbox_path).resolve()
            source_artifact_ids = list(baseline.artifact_ids or [])
            source_artifact_ids.extend(artifact for row in validations for artifact in (row.artifact_ids or []))
            baseline_checksum = baseline.checksum
            runtime_profile_id = profile.selected_profile_id if profile else None
            runtime_checksum = profile.selected_checksum if profile else None
            installations = session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id)).all()
            source_artifact_ids.extend(artifact for row in installations for artifact in (row.artifact_ids or []))

        store = LocalFilesystemArtifactStore(run_root, fixed_run_root=run_root)
        failures, diagnostics = self._failures(validations, installations, store)
        route_anchor = RouteInventoryBuilder().build(sandbox)
        backend_anchor = BackendContractSnapshotBuilder().build(sandbox)
        confidence = {
            "failures": EvidenceConfidence.MACHINE_PROVEN.value if validations else EvidenceConfidence.UNKNOWN.value,
            "routes": route_anchor.confidence.value if route_anchor.value else EvidenceConfidence.UNKNOWN.value,
            "backend_integration": backend_anchor.confidence.value if backend_anchor.value else EvidenceConfidence.UNKNOWN.value,
            "package_runtime": EvidenceConfidence.MACHINE_PROVEN.value if profile else EvidenceConfidence.UNKNOWN.value,
            "anchors": EvidenceConfidence.MACHINE_PROVEN.value if profile or validations else EvidenceConfidence.UNKNOWN.value,
        }
        routes = route_anchor.value if isinstance(route_anchor.value, list) else []
        backend_integration = backend_anchor.value if isinstance(backend_anchor.value, dict) else {}
        anchors = [
            {"name": "baseline_target_inventory", "value": [row.targets for row in validations], "confidence": confidence["failures"], "schema_version": SCHEMA_VERSION},
            {"name": "package_runtime", "value": {"baseline_checksum": baseline_checksum, "runtime_profile_id": runtime_profile_id, "runtime_checksum": runtime_checksum}, "confidence": confidence["package_runtime"], "schema_version": SCHEMA_VERSION},
        ]
        payloads = {
            "known_baseline_failures.json": {"schema_version": SCHEMA_VERSION, "parser_version": PARSER_VERSION, "failures": failures, "diagnostics": diagnostics},
            "baseline_route_inventory.json": {"schema_version": SCHEMA_VERSION, "confidence": confidence["routes"], "routes": routes},
            "baseline_backend_integration_snapshot.json": {"schema_version": SCHEMA_VERSION, "confidence": confidence["backend_integration"], "snapshot": backend_integration},
            "baseline_anchor_manifest.json": {"schema_version": SCHEMA_VERSION, "parser_version": PARSER_VERSION, "anchors": anchors, "confidence": confidence},
            "baseline_parser_diagnostics.json": {"schema_version": SCHEMA_VERSION, "parser_version": PARSER_VERSION, "diagnostics": diagnostics},
        }
        store = LocalFilesystemArtifactStore(run_root, fixed_run_root=run_root)
        stored = [store.write_text_artifact(run_id, f"01_baseline/{name}", json.dumps(value, indent=2, sort_keys=True), ArtifactType.JSON, created_by="baseline-parity-service", created_at=self._now(), input_hashes={"baseline": baseline_checksum or ""}, policy_version=PARSER_VERSION) for name, value in payloads.items()]
        artifact_ids = [item.ref.artifact_id for item in stored]
        artifact_checksums = {item.ref.artifact_id: item.ref.checksum for item in stored}

        with self._scope() as session:
            run, _ = self._run_and_baseline(session, run_id)
            self._require_state(run, request.expected_state_version)
            event_keys = ("failures", "routes", "backend")
            event_types = (WorkflowEventType.BASELINE_FAILURES_FINGERPRINTED, WorkflowEventType.BASELINE_ROUTE_ANCHOR_CREATED, WorkflowEventType.BASELINE_BACKEND_ANCHOR_CREATED)
            transition = None
            for suffix, event_type in zip(event_keys, event_types):
                transition = self._transition(session, run, request, event_type, f"baseline {suffix} parity evidence created", {"schema_version": SCHEMA_VERSION, "artifact_count": len(artifact_ids)}, expected_state_version=run.state_version)
            record = BaselineParityEvidenceModel(id=f"parity-{uuid4().hex[:12]}", run_id=run_id, idempotency_key=request.idempotency_key, actor=request.actor, status="captured", parser_version=PARSER_VERSION, schema_version=SCHEMA_VERSION, baseline_checksum=baseline_checksum, runtime_profile_id=runtime_profile_id, runtime_checksum=runtime_checksum, failures=failures, routes=routes, backend_integration=backend_integration, anchors=anchors, diagnostics=diagnostics, confidence=confidence, source_artifact_ids=sorted(set(source_artifact_ids)), artifact_ids=artifact_ids, artifact_checksums=artifact_checksums, state_version=transition.next_state_version, event_sequence=transition.event_sequence, created_at=self._now(), updated_at=self._now())
            session.add(record)
            for artifact in stored:
                session.add(ArtifactMetadataModel(id=f"metadata-{artifact.ref.artifact_id}", run_id=run_id, stage_id=None, artifact_type=artifact.ref.artifact_type.value, relative_path=artifact.ref.relative_path, checksum=artifact.ref.checksum, created_at=artifact.ref.created_at))
            session.flush()
            return self._response(record)

    def get(self, run_id: str, section: str) -> BaselineParityResponse | None:
        with self._scope() as session:
            record = session.scalar(select(BaselineParityEvidenceModel).where(BaselineParityEvidenceModel.run_id == run_id).order_by(BaselineParityEvidenceModel.created_at.desc()))
            if record is None:
                return None
            return self._response(record, section=section)

    def _failures(self, validations, installations, store):
        diagnostics = []
        for validation in validations:
            for result in validation.results or []:
                if result.get("status") != "failed":
                    continue
                for message in result.get("failed_tests", []) or result.get("warnings", []) or [result.get("blocker") or "baseline command failed"]:
                    diagnostics.append({"kind": result.get("kind", validation.kind), "message": message, "group": result.get("target_id")})
        for installation in installations:
            if installation.status not in {"FAILED", "TIMED_OUT", "CANCELLED"}:
                continue
            for blocker in installation.blockers or []:
                diagnostics.append({"kind": "install", "message": blocker})
            for artifact_id in installation.artifact_ids or []:
                try:
                    content = store.read_artifact_by_id(artifact_id).content
                except (OSError, ValueError):
                    continue
                for line in content.splitlines():
                    if line.strip():
                        diagnostics.append({"kind": "install", "message": line})
        failures = [self._jsonable(item) for item in self._fingerprints.from_diagnostics(diagnostics)]
        return failures, diagnostics

    @staticmethod
    def _jsonable(value):
        data = asdict(value)
        if isinstance(data.get("confidence"), EvidenceConfidence):
            data["confidence"] = data["confidence"].value
        return data

    def _run_and_baseline(self, session, run_id):
        run = session.get(MigrationRunModel, run_id)
        baseline = session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == run_id).order_by(BaselineQualificationModel.created_at.desc()))
        if run is None:
            raise BaselineParityApplicationError("RUN_NOT_FOUND", "Migration run was not found.", 404)
        if baseline is None or baseline.authorization_status != "authorized":
            raise BaselineParityApplicationError("BASELINE_INSTALL_AUTHORIZATION_REQUIRED", "An authorized baseline is required.", 409)
        return run, baseline

    @staticmethod
    def _require_state(run, expected):
        if run.state_version != expected:
            raise BaselineParityApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    @staticmethod
    def _require_prerequisites(session, run, baseline, artifact_ids, expected_checksums):
        metadata = {row.id.removeprefix("metadata-"): row for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run.id)).all()}
        missing = [item for item in artifact_ids if item not in metadata]
        if missing:
            raise BaselineParityApplicationError("PREREQUISITE_ARTIFACT_NOT_FOUND", "A prerequisite artifact is not registered.", 409)
        missing_checksums = [item for item in artifact_ids if not expected_checksums.get(item)]
        if missing_checksums:
            raise BaselineParityApplicationError("PREREQUISITE_ARTIFACT_CHECKSUM_REQUIRED", "Every prerequisite artifact requires an expected checksum.", 409)
        mismatched = [item for item in artifact_ids if metadata[item].checksum != expected_checksums[item]]
        if mismatched:
            raise BaselineParityApplicationError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite artifact checksum does not match the registered evidence.", 409)

    def _transition(self, session, run, request, event_type, reason, payload, *, expected_state_version):
        try:
            return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=expected_state_version, idempotency_key=f"{request.idempotency_key}:{event_type.value}", event_type=event_type, actor=request.actor, reason=reason, occurred_at=self._now(), payload=payload))
        except StaleStateVersionError as error:
            raise BaselineParityApplicationError("STALE_STATE_VERSION", str(error), 409) from error

    @staticmethod
    def _response(record, *, replay=False, section=None):
        return BaselineParityResponse(run_id=record.run_id, evidence_id=record.id, status=record.status, schema_version=record.schema_version, parser_version=record.parser_version, baseline_checksum=record.baseline_checksum, runtime_profile_id=record.runtime_profile_id, runtime_checksum=record.runtime_checksum, failures=record.failures if section in (None, "failures") else [], routes=record.routes if section in (None, "routes") else [], backend_integration=record.backend_integration if section in (None, "backend-integration") else {}, anchors=record.anchors if section in (None, "anchors") else [], confidence=record.confidence, source_artifact_ids=record.source_artifact_ids, artifact_ids=record.artifact_ids, artifact_checksums=record.artifact_checksums, state_version=record.state_version, event_sequence=record.event_sequence, idempotent_replay=replay)
