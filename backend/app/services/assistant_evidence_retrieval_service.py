"""Approved, immutable, checksum-bound evidence selection for Assistant context."""

from pathlib import Path
import json
import re

from sqlalchemy import select

from app.artifact_store.local_store import ArtifactNotFoundError, LocalFilesystemArtifactStore
from app.llm_gateway import LlmContextSegment
from app.repositories.models import (
    ArtifactMetadataModel,
    ExecutionProfileModel,
    G02ApprovalModel,
    MigrationRunModel,
    SourceSnapshotModel,
)

_SECRET = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+")


class AssistantEvidenceRetrievalService:
    allowed_types = frozenset({"json", "yaml", "markdown", "text_log", "command_log", "report"})

    @staticmethod
    def _terms(value: str) -> set[str]:
        return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 2}

    @staticmethod
    def _content(store: LocalFilesystemArtifactStore | None, row: ArtifactMetadataModel) -> tuple[str, str]:
        metadata = row.safe_metadata or {}
        artifact_id = row.id.removeprefix("metadata-")
        if store is not None:
            try:
                stored = store.read_artifact_by_id(artifact_id)
                if stored.ref.checksum == row.checksum:
                    return stored.content, "artifact_content"
            except (ArtifactNotFoundError, OSError, ValueError):
                pass
        return str(metadata.get("excerpt") or metadata.get("content") or row.relative_path), "safe_metadata.excerpt"

    def retrieve(
        self,
        session,
        run_id: str,
        question: str,
        *,
        stage_id: str | None = None,
        limit: int = 8,
    ) -> tuple[list[LlmContextSegment], list[dict[str, object]]]:
        rows = session.scalars(
            select(ArtifactMetadataModel).where(
                ArtifactMetadataModel.run_id == run_id,
                ArtifactMetadataModel.immutable.is_(True),
            )
        ).all()
        run = session.get(MigrationRunModel, run_id)
        store = None
        if run is not None and run.artifact_root:
            artifact_root = Path(run.artifact_root)
            store = LocalFilesystemArtifactStore(artifact_root, fixed_run_root=artifact_root)

        authoritative_ids: set[str] = set()
        snapshot = session.scalar(
            select(SourceSnapshotModel)
            .where(SourceSnapshotModel.run_id == run_id)
            .order_by(SourceSnapshotModel.created_at.desc())
        )
        g02 = session.scalar(
            select(G02ApprovalModel)
            .where(G02ApprovalModel.run_id == run_id)
            .order_by(G02ApprovalModel.updated_at.desc())
        )
        execution_profile = session.scalar(
            select(ExecutionProfileModel)
            .where(ExecutionProfileModel.run_id == run_id)
            .order_by(ExecutionProfileModel.updated_at.desc())
        )
        if snapshot is not None and snapshot.status == "created":
            authoritative_ids.update(snapshot.artifact_ids or [])
        if g02 is not None and g02.status == "approved":
            authoritative_ids.update(g02.artifact_ids or [])
        if execution_profile is not None:
            authoritative_ids.update(execution_profile.artifact_ids or [])
        canonical_authoritative_ids = authoritative_ids | {"metadata-" + item for item in authoritative_ids}

        question_terms = self._terms(question)
        candidates: list[tuple[int, ArtifactMetadataModel, str, str]] = []
        for row in rows:
            metadata = row.safe_metadata or {}
            approved_metadata = metadata.get("approval_status") == "approved"
            authorized_record = row.id in canonical_authoritative_ids or row.id.removeprefix("metadata-") in authoritative_ids
            if (not approved_metadata and not authorized_record) or row.artifact_type not in self.allowed_types:
                continue
            if stage_id and row.stage_id != stage_id:
                continue
            if row.redacted or not row.checksum or (not authorized_record and not str(metadata.get("lineage", "")).startswith(run_id)):
                continue
            content, locator = self._content(store, row)
            searchable = " ".join((row.relative_path, row.artifact_type, json.dumps(metadata, sort_keys=True), content[:4000]))
            overlap = len(question_terms & self._terms(searchable))
            authority_score = 4 if authorized_record else 2
            approval_score = 2 if approved_metadata else 0
            candidates.append((overlap * 10 + authority_score + approval_score, row, content, locator))

        candidates.sort(key=lambda item: (-item[0], item[1].relative_path))
        selected: list[LlmContextSegment] = []
        refs: list[dict[str, object]] = []
        for _, row, content, locator in candidates[:limit]:
            sanitized = _SECRET.sub("[REDACTED]", content)[:8000]
            selected.append(
                LlmContextSegment(
                    segment_id=f"artifact:{row.id}",
                    label=f"validated artifact {row.relative_path}",
                    content=sanitized,
                    artifact_ref=row.id,
                    untrusted=True,
                )
            )
            refs.append(
                {
                    "artifact_id": row.id,
                    "checksum": row.checksum,
                    "excerpt_locator": locator,
                    "evidence_type": row.artifact_type,
                    "proof_label": "approved_evidence_supported",
                    "label": row.relative_path,
                }
            )
        return selected, refs
