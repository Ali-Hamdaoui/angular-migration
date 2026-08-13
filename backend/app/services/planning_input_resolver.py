"""Resolve feasibility inputs from persisted workflow evidence."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re

from sqlalchemy import select

from app.api.compatibility_contracts import FeasibilityCreateRequest
from app.repositories.models import (
    ArtifactMetadataModel,
    CompatibilityCatalogueModel,
    EnvironmentCapabilityModel,
    ExecutionProfileModel,
    G04ApprovalModel,
    G03ApprovalModel,
    MigrationRunModel,
    RegistrySnapshotModel,
    SourceAnalysisModel,
    SourceSnapshotModel,
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
        workspace_fingerprint = self._workspace_fingerprint(session, run_id, gate)
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
                registry = RegistrySnapshotBuilder().build(session, run, source_angular_exact=source_exact)
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
        environment = session.scalar(select(EnvironmentCapabilityModel).order_by(EnvironmentCapabilityModel.created_at.desc()))
        configured = (environment.snapshot or {}).get("runtime_profiles", []) if environment else []
        if configured:
            network = (environment.snapshot or {}).get("network", {})
            registry_probe = ((environment.snapshot or {}).get("controlled_probes", {}).get("npm_registry", {}))
            runtime = tuple({
                "profile_id": item["profile_id"], "operating_system": "windows", "architecture": "amd64",
                "node_executable": item["node_executable"], "node_exact": item["node_exact"],
                "npm_executable": item["npm_executable"], "npm_exact": item["npm_exact"],
                "npx_executable": item["npx_executable"], "npx_exact": item["npx_exact"],
                "registry_configured": registry_probe.get("status") == "passed" and bool(registry_probe.get("value")),
                "proxy_configured": bool(network.get("proxy_configured") or network.get("https_proxy_configured")),
                "certificate_valid": bool(network.get("strict_ssl")),
                "environment_allowlist_valid": True, "cache_policy_valid": True,
                "network_policy": "approved-registries-only", "available": True,
            } for item in configured)
        return FeasibilityCreateRequest(
            expected_state_version=expected_state_version, idempotency_key=idempotency_key,
            source_angular_exact=source_exact, catalogue_version=catalogue.version,
            registry_snapshot_id=registry.snapshot_id, registry_snapshot_checksum=registry.checksum,
            prerequisite_artifacts=list(references), runtime_candidates=runtime,
            source_execution_profile_checksum=profile_record.selected_checksum,
            workspace_fingerprint=workspace_fingerprint,
            resolved_at=now,
        )

    @staticmethod
    def _workspace_fingerprint(session, run_id: str, gate: G04ApprovalModel) -> str:
        g03 = session.scalar(
            select(G03ApprovalModel)
            .where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.status == "approved")
            .order_by(G03ApprovalModel.updated_at.desc())
        )
        if g03 is None:
            raise PlanningInputResolutionError(
                "PLANNING_G03_BINDING_STALE",
                "A current approved G03 package is required before feasibility planning.",
            )
        if not g03.sandbox_fingerprint:
            raise PlanningInputResolutionError(
                "PLANNING_WORKSPACE_FINGERPRINT_MISSING",
                "The approved G03 package has no physical workspace fingerprint.",
            )
        if gate.workspace_fingerprint is not None and gate.workspace_fingerprint != g03.sandbox_fingerprint:
            raise PlanningInputResolutionError(
                "PLANNING_G04_WORKSPACE_FINGERPRINT_MISMATCH",
                "The approved G04 package is bound to a different workspace than G03.",
            )
        return gate.workspace_fingerprint or g03.sandbox_fingerprint

    @staticmethod
    def _exact_source_from_evidence(session, run: MigrationRunModel) -> str | None:
        if run.source_version_detected and re.fullmatch(r"\d+\.\d+\.\d+", run.source_version_detected):
            return run.source_version_detected
        preflight = session.get(PreflightModel, run.preflight_id) if run.preflight_id else None
        analysis = session.get(SourceAnalysisModel, (preflight.binding or {}).get("source_analysis_id")) if preflight else None
        versions = (analysis.snapshot or {}).get("versions", []) if analysis else []
        exact = next((item.get("resolved") for item in versions if item.get("package") == "@angular/core" and re.fullmatch(r"\d+\.\d+\.\d+", str(item.get("resolved") or ""))), None)
        if exact is None:
            snapshot = session.scalar(
                select(SourceSnapshotModel)
                .where(
                    SourceSnapshotModel.run_id == run.id,
                    SourceSnapshotModel.status == "created",
                )
                .order_by(SourceSnapshotModel.updated_at.desc())
            )
            if snapshot is not None:
                exact = PlanningInputResolver._exact_angular_from_snapshot_lock(snapshot.snapshot_path)
        if exact:
            run.source_version_detected = exact
            run.source_version_family = f"angular-{exact.split('.', 1)[0]}.x"
        return exact

    @staticmethod
    def _exact_angular_from_snapshot_lock(snapshot_path: str) -> str | None:
        root = Path(snapshot_path)
        path = next(
            (candidate for candidate in (root / "package-lock.json", root / "npm-shrinkwrap.json") if candidate.is_file()),
            None,
        )
        if path is None:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        packages = payload.get("packages", {}) if isinstance(payload, dict) else {}
        modern = packages.get("node_modules/@angular/core", {}) if isinstance(packages, dict) else {}
        legacy_dependencies = payload.get("dependencies", {}) if isinstance(payload, dict) else {}
        legacy = legacy_dependencies.get("@angular/core", {}) if isinstance(legacy_dependencies, dict) else {}
        exact = modern.get("version") if isinstance(modern, dict) else None
        if exact is None and isinstance(legacy, dict):
            exact = legacy.get("version")
        return exact if isinstance(exact, str) and re.fullmatch(r"\d+\.\d+\.\d+", exact) else None
