"""Resolve feasibility inputs from persisted workflow evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.api.compatibility_contracts import FeasibilityCreateRequest
from app.repositories.models import (
    ArtifactMetadataModel,
    CompatibilityCatalogueModel,
    ExecutionProfileModel,
    G04ApprovalModel,
    MigrationRunModel,
    RegistrySnapshotModel,
)
from app.services.artifact_binding import canonical_artifact_references


class PlanningInputResolutionError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


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
        source_exact = run.source_version_detected or run.source_angular_version
        if not source_exact or source_exact.endswith(".x"):
            raise PlanningInputResolutionError("PLANNING_SOURCE_EVIDENCE_MISSING", "Persisted source evidence does not contain an exact Angular version.")
        source_family = run.source_version_family or f"angular-{source_exact.split('.', 1)[0]}.x"
        target_family = run.target_version_family or "angular-21.x"
        catalogue = session.scalar(select(CompatibilityCatalogueModel).order_by(CompatibilityCatalogueModel.created_at.desc()))
        if catalogue is None:
            raise PlanningInputResolutionError("PLANNING_CATALOGUE_EVIDENCE_MISSING", "No persisted compatibility catalogue snapshot is available.")
        registry = session.scalar(select(RegistrySnapshotModel).where(RegistrySnapshotModel.run_id == run_id).order_by(RegistrySnapshotModel.created_at.desc()))
        if registry is None:
            raise PlanningInputResolutionError("PLANNING_REGISTRY_EVIDENCE_MISSING", "No persisted registry snapshot is available.")
        profile_record = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.created_at.desc()))
        if profile_record is None or not profile_record.selected_profile_id or not profile_record.selected_checksum:
            raise PlanningInputResolutionError("PLANNING_RUNTIME_PROFILE_MISSING", "No selected persisted execution profile is available.")
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
            workspace_fingerprint=gate.workspace_fingerprint,
            resolved_at=now,
        )
