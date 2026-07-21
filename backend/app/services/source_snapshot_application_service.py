"""Application service for durable source snapshot creation and inspection."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, RunStatus, WorkflowEventType
from app.domain.snapshot import (
    CreateSourceSnapshotRequest,
    SnapshotStatus,
    SourceSnapshotDto,
)
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel, SourceSnapshotModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.repositories.source_snapshots import SourceSnapshotRepository
from app.snapshots import SnapshotIntegrityError, SnapshotService
from app.state.transition_service import StateTransitionService, TransitionRequest


class SnapshotApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SourceSnapshotApplicationService:
    """Coordinate filesystem evidence, persistence, artifacts, and run transitions."""

    _ALLOWED_STATUSES = {RunStatus.CREATED.value, RunStatus.SOURCE_VALIDATION_RUNNING.value}

    def __init__(
        self,
        settings,
        *,
        session_scope_factory=session_scope,
        snapshot_service_factory=None,
        now_provider=None,
    ) -> None:
        self._settings = settings
        self._scope = session_scope_factory
        self._snapshot_factory = snapshot_service_factory or self._default_snapshot_service
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._repository = SourceSnapshotRepository()

    def create(
        self, run_id: str, request: CreateSourceSnapshotRequest
    ) -> SourceSnapshotDto:
        with self._scope() as session:
            existing = self._repository.get_by_idempotency(
                session, run_id, request.idempotency_key
            )
            if existing is not None:
                return self._to_dto(session, existing, idempotent_replay=True)
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise SnapshotApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            if run.status not in self._ALLOWED_STATUSES:
                raise SnapshotApplicationError(
                    "SNAPSHOT_NOT_ALLOWED",
                    "The run is not in a state that allows source snapshot creation.",
                    status_code=409,
                )
            if run.state_version != request.expected_state_version:
                raise SnapshotApplicationError(
                    "STALE_STATE_VERSION",
                    f"Run state version is {run.state_version}; expected {request.expected_state_version}.",
                    status_code=409,
                )
            started = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=f"{request.idempotency_key}:started",
                    event_type=WorkflowEventType.SNAPSHOT_STARTED,
                    next_run_status=RunStatus.SOURCE_VALIDATION_RUNNING,
                    actor=request.actor,
                    reason="source snapshot acquisition started",
                    occurred_at=self._now(),
                )
            )
            snapshot_id = f"snapshot-{uuid4().hex[:12]}"
            source_path = run.source_path
            snapshot_path = (run.workspace_aliases or {}).get("SOURCE_SNAPSHOT")
            if not source_path or not snapshot_path:
                raise SnapshotApplicationError(
                    "SNAPSHOT_LAYOUT_MISSING",
                    "The run does not contain registered source and snapshot paths.",
                )
            progress = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=started.next_state_version,
                    idempotency_key=f"{request.idempotency_key}:progress",
                    event_type=WorkflowEventType.SNAPSHOT_PROGRESS_UPDATED,
                    actor=request.actor,
                    reason="source snapshot acquisition is copying files",
                    occurred_at=self._now(),
                    payload={"snapshot_id": snapshot_id, "phase": "copying"},
                )
            )
        try:
            record = self._snapshot_factory(Path(snapshot_path)).create_snapshot(
                Path(source_path), snapshot_id
            )
        except SnapshotIntegrityError as error:
            return self._persist_failure(
                run_id, request, snapshot_id, str(error), "SOURCE_CHANGED_DURING_COPY", progress.next_state_version
            )
        except (OSError, ValueError) as error:
            return self._persist_failure(
                run_id, request, snapshot_id, str(error), "SNAPSHOT_CREATION_FAILED", progress.next_state_version
            )

        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise SnapshotApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            artifacts = self._write_artifacts(session, run, record, now)
            result = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=WorkflowEventType.SNAPSHOT_CREATED,
                    next_run_status=RunStatus.SOURCE_VALIDATED,
                    actor=request.actor,
                    reason="immutable source snapshot created and evidence finalized",
                    occurred_at=now,
                    payload={
                        "snapshot_id": record.snapshot_id,
                        "fingerprint": record.fingerprint,
                        "artifact_count": len(artifacts),
                    },
                )
            )
            model = SourceSnapshotModel(
                id=record.snapshot_id,
                run_id=run_id,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                status=SnapshotStatus.CREATED.value,
                source_path=str(record.manifest.source_root),
                snapshot_path=str(record.snapshot_root),
                manifest_id=record.manifest.manifest_id,
                fingerprint=record.fingerprint,
                policy_version=record.manifest.policy_version,
                file_count=len(record.manifest.entries),
                total_size_bytes=sum(item.size_bytes for item in record.manifest.entries),
                exclusions=[asdict(item) for item in record.manifest.exclusions],
                git_metadata=asdict(record.git_metadata),
                artifact_ids=[item.artifact_id for item in artifacts],
                state_version=result.next_state_version,
                event_sequence=result.event_sequence,
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            return self._to_dto(session, model)

    def get(self, run_id: str, snapshot_id: str) -> SourceSnapshotDto | None:
        with self._scope() as session:
            model = self._repository.get_by_id(session, snapshot_id)
            if model is None or model.run_id != run_id:
                return None
            return self._to_dto(session, model)

    def _persist_failure(
        self,
        run_id: str,
        request: CreateSourceSnapshotRequest,
        snapshot_id: str,
        message: str,
        code: str,
        expected_state_version: int,
    ) -> SourceSnapshotDto:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            result = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=expected_state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=WorkflowEventType.SNAPSHOT_FAILED,
                    actor=request.actor,
                    reason="source snapshot acquisition failed",
                    occurred_at=now,
                    payload={"snapshot_id": snapshot_id, "error_code": code},
                )
            )
            quarantined = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=result.next_state_version,
                    idempotency_key=f"{request.idempotency_key}:quarantined",
                    event_type=WorkflowEventType.SNAPSHOT_QUARANTINED,
                    actor=request.actor,
                    reason="incomplete source snapshot copy was safely removed",
                    occurred_at=now,
                    payload={"snapshot_id": snapshot_id, "cleanup": "removed"},
                )
            )
            model = SourceSnapshotModel(
                id=snapshot_id,
                run_id=run_id,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                status=SnapshotStatus.FAILED.value,
                source_path=run.source_path or "",
                snapshot_path=str((run.workspace_aliases or {}).get("SOURCE_SNAPSHOT", "")),
                policy_version="source-snapshot-policy-v1",
                exclusions=[],
                git_metadata={},
                artifact_ids=[],
                state_version=quarantined.next_state_version,
                event_sequence=quarantined.event_sequence,
                error_code=code,
                error_message=message,
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            return self._to_dto(session, model)

    def _default_snapshot_service(self, snapshot_root: Path) -> SnapshotService:
        return SnapshotService(
            snapshot_root,
            platform_repository_root=self._settings.platform_repository_root,
        )

    def _write_artifacts(self, session, run: MigrationRunModel, record, now: datetime) -> list[ArtifactRefDto]:
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        manifest = record.manifest
        manifest_payload = {
            "manifest_id": manifest.manifest_id,
            "source_root": manifest.source_root,
            "generated_at": manifest.generated_at.isoformat(),
            "checksum": manifest.checksum,
            "policy_version": manifest.policy_version,
            "entries": [asdict(entry) for entry in manifest.entries],
            "exclusions": [asdict(item) for item in manifest.exclusions],
        }
        evidence = {
            "source_manifest.json": manifest_payload,
            "source_git_metadata.json": asdict(record.git_metadata),
            "snapshot_manifest.json": {
                "snapshot_id": record.snapshot_id,
                "snapshot_path": str(record.snapshot_root),
                "manifest_id": manifest.manifest_id,
                "file_count": len(manifest.entries),
                "total_size_bytes": sum(item.size_bytes for item in manifest.entries),
            },
            "exclusion_policy_snapshot.json": {
                "policy_version": manifest.policy_version,
                "exclusions": [asdict(item) for item in manifest.exclusions],
            },
            "snapshot_copy_report.json": {
                "status": SnapshotStatus.CREATED.value,
                "snapshot_id": record.snapshot_id,
                "source_path": manifest.source_root,
            },
            "snapshot_fingerprint.json": {
                "fingerprint": record.fingerprint,
                "manifest_checksum": manifest.checksum,
            },
        }
        refs: list[ArtifactRefDto] = []
        for name, payload in evidence.items():
            stored = store.write_text_artifact(
                run.id,
                f"global/source-snapshots/{record.snapshot_id}/{name}",
                json.dumps(payload, indent=2, sort_keys=True),
                ArtifactType.JSON,
                created_by="source-snapshot-service",
                created_at=now,
                input_hashes={"source_fingerprint": record.fingerprint},
                policy_version=manifest.policy_version,
            )
            refs.append(stored.ref)
            session.add(
                ArtifactMetadataModel(
                    id=f"metadata-{stored.ref.artifact_id}",
                    run_id=run.id,
                    stage_id=None,
                    artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path,
                    checksum=stored.ref.checksum,
                    created_at=now,
                )
            )
        validation_payload = {
            "status": "passed",
            "source_path": str(manifest.source_root),
            "snapshot_path": str(record.snapshot_root),
            "file_count": len(manifest.entries),
            "total_included_size": sum(item.size_bytes for item in manifest.entries),
            "exclusion_count": len(manifest.exclusions),
            "source_fingerprint": record.fingerprint,
            "snapshot_fingerprint": record.fingerprint,
            "copy_verification": "passed",
            "blockers": [],
            "warnings": [],
            "created_at": now.isoformat(),
            "evidence_artifact_ids": [ref.artifact_id for ref in refs],
        }
        stored = store.write_text_artifact(
            run.id,
            f"global/source-snapshots/{record.snapshot_id}/source_validation_result.json",
            json.dumps(validation_payload, indent=2, sort_keys=True),
            ArtifactType.JSON,
            created_by="source-snapshot-service",
            created_at=now,
            input_hashes={"source_fingerprint": record.fingerprint},
            policy_version=manifest.policy_version,
        )
        refs.append(stored.ref)
        session.add(ArtifactMetadataModel(id=f"metadata-{stored.ref.artifact_id}", run_id=run.id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))
        return refs

    def _to_dto(self, session, model: SourceSnapshotModel, *, idempotent_replay: bool = False) -> SourceSnapshotDto:
        artifact_ids = set(model.artifact_ids or [])
        refs = [
            ArtifactRefDto(
                artifact_id=row.id.removeprefix("metadata-"),
                run_id=model.run_id,
                stage_id=row.stage_id,
                artifact_type=ArtifactType(row.artifact_type),
                relative_path=row.relative_path,
                created_at=row.created_at,
                checksum=row.checksum,
            )
            for row in session.scalars(
                select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == model.run_id)
            )
            if row.id.removeprefix("metadata-") in artifact_ids
        ]
        return SourceSnapshotDto(
            snapshot_id=model.id,
            run_id=model.run_id,
            status=SnapshotStatus(model.status),
            source_path=model.source_path,
            snapshot_path=model.snapshot_path,
            manifest_id=model.manifest_id,
            fingerprint=model.fingerprint,
            policy_version=model.policy_version,
            file_count=model.file_count,
            total_size_bytes=model.total_size_bytes,
            exclusions=model.exclusions or [],
            git_metadata=model.git_metadata or {},
            artifacts=refs,
            state_version=model.state_version,
            event_sequence=model.event_sequence,
            idempotent_replay=idempotent_replay,
            error_code=model.error_code,
            error_message=model.error_message,
            created_at=model.created_at,
        )
