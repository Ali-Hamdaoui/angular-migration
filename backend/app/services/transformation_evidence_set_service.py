"""Service for writing, registering, verifying, and cleaning up transformation evidence artifact sets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select

from app.artifact_store.local_store import StoredArtifact
from app.domain.contracts import ArtifactRefDto
from app.repositories.models import ArtifactMetadataModel
from app.repositories.transformation_models import TransformationEvidenceModel


@dataclass
class EvidenceSetResult:
    artifact_refs: list[ArtifactRefDto] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    manifest: dict | None = None
    artifact_set_checksum: str = ""


@dataclass
class VerificationResult:
    valid: bool = True
    error_code: str | None = None
    error_message: str | None = None


class TransformationEvidenceSetService:

    def write_artifact_set(
        self,
        session,
        store,
        run_id: str,
        stage_id: str,
        artifacts: dict[str, tuple[str, object, str]],
        now: datetime,
    ) -> EvidenceSetResult:
        evidence = session.scalar(
            select(TransformationEvidenceModel)
            .where(
                TransformationEvidenceModel.run_id == run_id,
                TransformationEvidenceModel.stage_id == stage_id,
            )
            .order_by(TransformationEvidenceModel.created_at.desc())
        )

        stored_artifacts: list[StoredArtifact] = []
        artifact_refs: list[ArtifactRefDto] = []
        artifact_ids: list[str] = []
        manifest_artifacts: list[dict] = []

        for kind, (content, artifact_type, filename) in artifacts.items():
            stored = store.write_text_artifact(
                run_id,
                f"stages/{stage_id}/evidence/{filename}",
                content,
                artifact_type,
                stage_id=stage_id,
                created_by="transformation-evidence-set-service",
                created_at=now,
            )
            session.add(
                ArtifactMetadataModel(
                    id=f"metadata-{stored.ref.artifact_id}",
                    run_id=run_id,
                    stage_id=stage_id,
                    artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path,
                    checksum=stored.ref.checksum,
                    created_at=now,
                )
            )
            stored_artifacts.append(stored)
            artifact_refs.append(stored.ref)
            artifact_ids.append(stored.ref.artifact_id)
            manifest_artifacts.append(
                {
                    "kind": kind,
                    "artifact_id": stored.ref.artifact_id,
                    "artifact_type": stored.ref.artifact_type.value,
                    "checksum": stored.ref.checksum,
                    "size_bytes": len(content.encode("utf-8")),
                    "relative_path": stored.ref.relative_path,
                }
            )

        evidence_id = evidence.id if evidence else ""
        angular_update_record_id = evidence.angular_update_record_id if evidence else ""
        angular_update_binding_checksum = evidence.angular_update_binding_checksum if evidence else ""
        input_fingerprint = evidence.input_fingerprint if evidence else ""
        target_fingerprint = evidence.target_fingerprint if evidence else ""

        manifest: dict = {
            "schema_version": "transformation-artifact-set-v1",
            "run_id": run_id,
            "stage_id": stage_id,
            "evidence_id": evidence_id,
            "angular_update_record_id": angular_update_record_id,
            "angular_update_binding_checksum": angular_update_binding_checksum,
            "input_fingerprint": input_fingerprint,
            "target_fingerprint": target_fingerprint,
            "artifacts": manifest_artifacts,
        }

        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        artifact_set_checksum = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()

        return EvidenceSetResult(
            artifact_refs=artifact_refs,
            artifact_ids=artifact_ids,
            manifest=manifest,
            artifact_set_checksum=artifact_set_checksum,
        )

    def verify_artifact_set(
        self,
        session,
        store,
        run_id: str,
        stage_id: str,
        expected_artifacts: dict[str, tuple[str, object, str]],
    ) -> VerificationResult:
        for kind in expected_artifacts:
            metadata = session.scalar(
                select(ArtifactMetadataModel)
                .where(
                    ArtifactMetadataModel.run_id == run_id,
                    ArtifactMetadataModel.stage_id == stage_id,
                    ArtifactMetadataModel.relative_path.like(f"%{kind}%"),
                )
            )
            if metadata is None:
                return VerificationResult(
                    valid=False,
                    error_code="ARTIFACT_MISSING",
                    error_message=f"Required artifact kind '{kind}' is missing from the store.",
                )

            if metadata.run_id != run_id or metadata.stage_id != stage_id:
                return VerificationResult(
                    valid=False,
                    error_code="ARTIFACT_OWNERSHIP",
                    error_message=f"Artifact '{kind}' does not belong to this run or stage.",
                )

            try:
                stored = store.read_artifact(run_id, metadata.relative_path)
            except (OSError, ValueError, KeyError):
                return VerificationResult(
                    valid=False,
                    error_code="ARTIFACT_UNREADABLE",
                    error_message=f"Artifact '{kind}' could not be read from the store.",
                )

            if stored.ref.checksum != metadata.checksum:
                return VerificationResult(
                    valid=False,
                    error_code="ARTIFACT_CHECKSUM_MISMATCH",
                    error_message=f"Checksum mismatch for artifact '{kind}'.",
                )

        return VerificationResult(valid=True)

    def rollback_uncommitted(
        self,
        session,
        store,
        run_id: str,
        stage_id: str,
        stored_artifacts: list[StoredArtifact],
    ) -> None:
        for stored in stored_artifacts:
            store.delete_artifact_version(stored)
            existing = session.get(ArtifactMetadataModel, f"metadata-{stored.ref.artifact_id}")
            if existing is not None:
                session.delete(existing)
