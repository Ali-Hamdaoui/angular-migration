"""Build run-bound registry probe snapshots from persisted preflight evidence."""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import select

from app.repositories.models import EnvironmentCapabilityModel, RegistrySnapshotModel, SourceAnalysisModel
from app.repositories.preflight_models import PreflightModel


class RegistrySnapshotBuildError(ValueError):
    pass


class RegistrySnapshotBuilder:
    def build(self, session, run) -> RegistrySnapshotModel:
        preflight = session.get(PreflightModel, run.preflight_id) if run.preflight_id else None
        binding = preflight.binding if preflight else None
        if not binding:
            raise RegistrySnapshotBuildError("The run has no preflight evidence binding.")
        environment = session.get(EnvironmentCapabilityModel, binding.get("environment_snapshot_id"))
        analysis = session.get(SourceAnalysisModel, binding.get("source_analysis_id"))
        probe = ((environment.snapshot if environment else {}) .get("controlled_probes", {}).get("npm_registry", {}))
        if environment is None or analysis is None or probe.get("status") != "passed" or not probe.get("value"):
            raise RegistrySnapshotBuildError("Approved environment registry-probe evidence is unavailable.")
        versions = (analysis.snapshot or {}).get("versions", [])
        packages = []
        for item in versions:
            # V2.2 P0-0: retain every queried package metadata row instead of
            # filtering to Core/TypeScript/RxJS; dependency planning owns the
            # interpretation. Registry identity/checksum binding is unchanged.
            resolved = item.get("resolved") or self._single_version(item.get("declared"))
            if resolved:
                packages.append({"package": item.get("package"), "declared": item.get("declared"), "resolved": resolved})
        if not any(item["package"] == "@angular/core" for item in packages):
            raise RegistrySnapshotBuildError("Source analysis lacks resolved @angular/core evidence.")
        payload = {
            "run_id": run.id,
            "registry_identity": probe["value"],
            "probe_timestamp": environment.captured_at.isoformat(),
            "probe_artifact_id": probe.get("artifact_id"),
            "environment_snapshot_id": environment.id,
            "environment_checksum": environment.checksum,
            "source_analysis_id": analysis.id,
            "source_analysis_checksum": analysis.checksum,
            "queried_package_versions": packages,
        }
        checksum = "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        snapshot_id = f"registry-{run.id}-{checksum[7:19]}"
        existing = session.scalar(
            select(RegistrySnapshotModel).where(
                RegistrySnapshotModel.run_id == run.id,
                RegistrySnapshotModel.checksum == checksum,
            )
        )
        if existing is not None:
            return existing
        record = RegistrySnapshotModel(id=f"registry-record-{checksum[7:19]}", run_id=run.id, snapshot_id=snapshot_id, checksum=checksum, metadata_json=payload, created_at=environment.captured_at)
        session.add(record)
        session.flush()
        return record

    @staticmethod
    def _single_version(value: object) -> str | None:
        match = re.fullmatch(r"[~^=]?\s*(\d+\.\d+\.\d+)", str(value or "").strip())
        return match.group(1) if match else None
