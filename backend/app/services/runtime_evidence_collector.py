"""Harness-specific runtime evidence collector.

Records deterministic evidence artifacts (fixture manifests, isolation evidence,
output layout, integration results, proof reports) using the atomic write + SHA-256
checksum pattern from LocalFilesystemArtifactStore.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType
from app.repositories.models import ArtifactMetadataModel


@dataclass(frozen=True)
class EvidenceWriteResult:
    """Result of writing a single evidence artifact."""

    ref: ArtifactRefDto
    run_id: str
    relative_path: str


class RuntimeEvidenceCollector:
    """Records harness evidence artifacts with atomic writes and checksum verification.

    Each record_* method writes one or more artifacts through the configured
    LocalFilesystemArtifactStore and registers an ArtifactMetadataModel entry.
    """

    def __init__(
        self,
        settings,
        *,
        artifact_store: LocalFilesystemArtifactStore | None = None,
        session_scope_factory=None,
    ) -> None:
        self._settings = settings
        self._store = artifact_store or self._default_store(settings)
        self._scope = session_scope_factory
        self._now = lambda: datetime.now(UTC)

    # ------------------------------------------------------------------
    # Public record methods
    # ------------------------------------------------------------------

    def record_fixture_manifest(
        self,
        run_id: str,
        fixture_type: str,
        root: str,
        checksum: str,
    ) -> ArtifactRefDto:
        """Record the fixture generation manifest as evidence."""
        payload = {
            "fixture_type": fixture_type,
            "root": str(root),
            "checksum": checksum,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/fixture_manifest_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_isolation_evidence(
        self,
        run_id: str,
        fixture_root: str,
        output_root: str,
    ) -> ArtifactRefDto:
        """Record isolation boundary evidence (fixture root + output root)."""
        payload = {
            "fixture_root": str(fixture_root),
            "output_root": str(output_root),
            "isolated": True,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/isolation_evidence_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_output_layout_evidence(
        self,
        run_id: str,
        layout: dict,
    ) -> ArtifactRefDto:
        """Record the output directory layout structure as evidence."""
        payload = {
            "layout": layout,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/output_layout_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_integration_result(
        self,
        run_id: str,
        result: dict,
        duration_ms: int,
    ) -> ArtifactRefDto:
        """Record an integration subprocess result as evidence."""
        payload = {
            "result": result,
            "duration_ms": duration_ms,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/integration_result_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_proof_report(
        self,
        run_id: str,
        summary: str,
    ) -> ArtifactRefDto:
        """Record a proof report as markdown evidence."""
        payload = {
            "summary": summary,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/proof_report_{uuid4().hex[:8]}.md",
            content=summary,
            artifact_type=ArtifactType.MARKDOWN,
        )

    # ------------------------------------------------------------------
    # T02 / AMFA-283 — new evidence record methods
    # ------------------------------------------------------------------

    def record_cancellation_evidence(
        self,
        run_id: str,
        fixture_id: str,
        fixture_root: str,
        reason: str,
        cancel_event_type: str,
    ) -> ArtifactRefDto:
        """Record cancellation event metadata, reason, and context as evidence."""
        payload = {
            "fixture_id": fixture_id,
            "fixture_root": str(fixture_root),
            "reason": reason,
            "cancel_event_type": cancel_event_type,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/cancellation_evidence_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_restart_evidence(
        self,
        run_id: str,
        fixture_id: str,
        fixture_root: str,
        restart_context: dict[str, object],
    ) -> ArtifactRefDto:
        """Record restart event metadata including previous evidence refs and state."""
        payload = {
            "fixture_id": fixture_id,
            "fixture_root": str(fixture_root),
            "restart_context": restart_context,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/restart_evidence_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_repair_lineage(
        self,
        run_id: str,
        fixture_id: str,
        repair_attempts: list[dict[str, object]],
        repair_artifacts: list[dict[str, object]],
    ) -> ArtifactRefDto:
        """Record the full repair lineage: attempts, diagnosis, patches, outcome."""
        payload = {
            "fixture_id": fixture_id,
            "repair_attempts": repair_attempts,
            "repair_artifacts": repair_artifacts,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/repair_lineage_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_output_fingerprint(
        self,
        run_id: str,
        fixture_id: str,
        artifact_root: str,
        fingerprint_data: dict[str, object],
    ) -> ArtifactRefDto:
        """Record SHA-256 fingerprints of the build output directory."""
        payload = {
            "fixture_id": fixture_id,
            "artifact_root": str(artifact_root),
            "fingerprint": fingerprint_data,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/output_fingerprint_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_source_integrity_proof(
        self,
        run_id: str,
        fixture_id: str,
        source_path: str,
        checksum: str,
        manifest: dict[str, object],
    ) -> ArtifactRefDto:
        """Record source integrity verification evidence."""
        payload = {
            "fixture_id": fixture_id,
            "source_path": str(source_path),
            "checksum": checksum,
            "manifest": manifest,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/source_integrity_proof_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    def record_acceptance_suite_evidence(
        self,
        run_id: str,
        aggregate_summary: dict[str, object],
        fixture_results: list[dict[str, object]],
    ) -> ArtifactRefDto:
        """Record the complete acceptance suite run aggregate as evidence."""
        payload = {
            "aggregate_summary": aggregate_summary,
            "fixture_results": fixture_results,
            "recorded_at": self._now().isoformat(),
        }
        return self._write_and_register(
            run_id=run_id,
            relative_path=f"00_job_setup/acceptance_suite_{uuid4().hex[:8]}.json",
            content=json.dumps(payload, sort_keys=True, indent=2),
            artifact_type=ArtifactType.JSON,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_and_register(
        self,
        *,
        run_id: str,
        relative_path: str,
        content: str,
        artifact_type: ArtifactType,
    ) -> ArtifactRefDto:
        """Write an artifact through the store and register its metadata."""
        now = self._now()
        stored = self._store.write_text_artifact(
            run_id,
            relative_path,
            content,
            artifact_type,
            created_by="runtime-evidence-collector",
            created_at=now,
            input_hashes={},
            policy_version="harness-v1",
        )
        if self._scope:
            with self._scope() as session:
                session.add(
                    ArtifactMetadataModel(
                        id=f"metadata-{stored.ref.artifact_id}",
                        run_id=run_id,
                        stage_id=None,
                        artifact_type=stored.ref.artifact_type.value,
                        relative_path=stored.ref.relative_path,
                        checksum=stored.ref.checksum,
                        created_at=now,
                    )
                )
        return stored.ref

    @staticmethod
    def _default_store(settings) -> LocalFilesystemArtifactStore:
        """Create a default LocalFilesystemArtifactStore from settings."""
        root = (
            Path(settings.artifact_root)
            if settings.artifact_root
            else Path(settings.platform_repository_root) / "data" / "artifacts"
        )
        return LocalFilesystemArtifactStore(root)
