"""Resolve feasibility inputs from persisted workflow evidence."""

from __future__ import annotations

from datetime import UTC, datetime
import re

from sqlalchemy import select

from app.api.compatibility_contracts import FeasibilityCreateRequest
from app.repositories.models import (
    ArtifactMetadataModel,
    CompatibilityCatalogueModel,
    ExecutionProfileModel,
    G04ApprovalModel,
    MigrationRunModel,
    RegistrySnapshotModel,
    SourceAnalysisModel,
)
from app.repositories.preflight_models import PreflightModel
from app.services.artifact_binding import canonical_artifact_references
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.registry_snapshot_builder import RegistrySnapshotBuildError, RegistrySnapshotBuilder


class PlanningInputResolutionError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409, *, details=None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class PlanningInputResolver:
    """Derive stable inputs without trusting browser-supplied authority."""

    def resolve(self, session, run_id: str, *, actor: str, expected_state_version: int, idempotency_key: str, now: datetime | None = None) -> FeasibilityCreateRequest:
        now = now or datetime.now(UTC)
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise PlanningInputResolutionError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.actor and run.actor != actor:
            raise PlanningInputResolutionError("RUN_NOT_AUTHORIZED", "Authenticated actor is not authorized for this run.", 403)
        gate = session.scalar(select(G04ApprovalModel).where(G04ApprovalModel.run_id == run_id, G04ApprovalModel.gate_id == "G04", G04ApprovalModel.status == "approved").order_by(G04ApprovalModel.state_version.desc(), G04ApprovalModel.created_at.desc()))
        if gate is None:
            raise PlanningInputResolutionError("PLANNING_G04_BINDING_STALE", "A current approved G04 package is required before feasibility planning.")
        source_exact = self._exact_source_from_evidence(session, run)
        if source_exact is None:
            raise PlanningInputResolutionError("PLANNING_SOURCE_EVIDENCE_MISSING", "Persisted source evidence does not contain an exact Angular version.")
        source_family = run.source_version_family or f"angular-{source_exact.split('.', 1)[0]}.x"
        target_family = run.target_version_family or "angular-21.x"
        catalogue = session.scalar(select(CompatibilityCatalogueModel).order_by(CompatibilityCatalogueModel.created_at.desc()))
        if catalogue is None:
            catalogue = CompatibilityCatalogueProvider().load()
        registry = session.scalar(select(RegistrySnapshotModel).where(RegistrySnapshotModel.run_id == run_id).order_by(RegistrySnapshotModel.created_at.desc()))
        if registry is None:
            try:
                registry = RegistrySnapshotBuilder().build(session, run)
            except RegistrySnapshotBuildError as error:
                raise PlanningInputResolutionError("PLANNING_REGISTRY_EVIDENCE_MISSING", str(error)) from error
        profile_record = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.created_at.desc()))
        if profile_record is None or not profile_record.selected_profile_id or not profile_record.selected_checksum:
            raise PlanningInputResolutionError("PLANNING_RUNTIME_PROFILE_MISSING", "No selected persisted execution profile is available.")
        if profile_record.source_angular_exact != source_exact:
            if profile_record.source_angular_exact.lstrip("^~") == source_exact:
                profile_record.source_angular_exact = source_exact
            else:
                raise PlanningInputResolutionError("PLANNING_SOURCE_PROFILE_MISMATCH", "The selected execution profile does not match the authoritative run source version.")
        profile = next((item for item in profile_record.profiles if item.get("profile_id") == profile_record.selected_profile_id and item.get("checksum") == profile_record.selected_checksum), None)
        if profile is None:
            raise PlanningInputResolutionError("PLANNING_RUNTIME_PROFILE_MISSING", "The selected execution profile evidence is incomplete.")
        raw_references = []
        for artifact_id in gate.artifact_ids:
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
            if metadata is None or metadata.run_id != run_id or not metadata.checksum:
                raise PlanningInputResolutionError("PLANNING_ARTIFACT_UNAVAILABLE", "An approved G04 artifact is unavailable or unregistered.")
            raw_references.append({"artifact_id": artifact_id, "checksum": metadata.checksum})
        references = canonical_artifact_references(raw_references)
        required_profile_fields = ("node_exact", "package_manager_exact", "npx_exact")
        if any(not profile.get(field) for field in required_profile_fields):
            raise PlanningInputResolutionError("PLANNING_RUNTIME_PROFILE_MISSING", "The selected execution profile lacks complete runtime evidence.")
        runtime = tuple({
            "profile_id": profile.get("profile_id"), "operating_system": profile.get("operating_system", "windows"), "architecture": profile.get("architecture", "amd64"),
            "node_executable": profile.get("node_executable", "node"), "node_exact": profile.get("node_exact", ""),
            "npm_executable": profile.get("package_manager_executable", "npm"), "npm_exact": profile.get("package_manager_exact", ""),
            "npx_executable": profile.get("npx_executable", "npx"), "npx_exact": profile.get("npx_exact", ""),
            "available": True,
        } for _ in [0])
        return FeasibilityCreateRequest(
            expected_state_version=expected_state_version, idempotency_key=idempotency_key,
            source_angular_exact=source_exact, catalogue_version=catalogue.version,
            registry_snapshot_id=registry.snapshot_id, registry_snapshot_checksum=registry.checksum,
            prerequisite_artifacts=list(references), runtime_candidates=runtime,
            source_execution_profile_checksum=profile_record.selected_checksum,
            workspace_fingerprint=gate.workspace_fingerprint,
            resolved_at=now,
        )

    @staticmethod
    def _exact_source_from_evidence(session, run: MigrationRunModel) -> str | None:
        if run.source_version_detected and re.fullmatch(r"\d+\.\d+\.\d+", run.source_version_detected):
            return run.source_version_detected
        preflight = session.get(PreflightModel, run.preflight_id) if run.preflight_id else None
        analysis = session.get(SourceAnalysisModel, (preflight.binding or {}).get("source_analysis_id")) if preflight else None
        versions = (analysis.snapshot or {}).get("versions", []) if analysis else []
        exact = next((item.get("resolved") for item in versions if item.get("package") == "@angular/core" and re.fullmatch(r"\d+\.\d+\.\d+", str(item.get("resolved") or ""))), None)
        if exact:
            run.source_version_detected = exact
            run.source_version_family = f"angular-{exact.split('.', 1)[0]}.x"
        return exact
