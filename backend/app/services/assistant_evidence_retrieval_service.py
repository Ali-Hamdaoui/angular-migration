"""Approved, immutable, checksum-bound evidence selection for Assistant context."""

import re
from sqlalchemy import select

from app.llm_gateway import LlmContextSegment
from app.repositories.models import ArtifactMetadataModel, ExecutionProfileModel, G02ApprovalModel, SourceSnapshotModel


class AssistantEvidenceRetrievalService:
    allowed_types = frozenset({"json", "yaml", "markdown", "text_log", "command_log", "report"})

    def retrieve(self, session, run_id: str, question: str, *, stage_id: str | None = None, limit: int = 8) -> tuple[list[LlmContextSegment], list[dict[str, object]]]:
        rows = session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id, ArtifactMetadataModel.immutable.is_(True))).all()
        authoritative_ids: set[str] = set()
        snapshot = session.scalar(select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run_id).order_by(SourceSnapshotModel.created_at.desc()))
        g02 = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.updated_at.desc()))
        execution_profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))
        if snapshot is not None and snapshot.status == 'created':
            authoritative_ids.update(snapshot.artifact_ids or [])
        if g02 is not None and g02.status == 'approved':
            authoritative_ids.update(g02.artifact_ids or [])
        if execution_profile is not None:
            authoritative_ids.update(execution_profile.artifact_ids or [])
        canonical_authoritative_ids = authoritative_ids | {'metadata-' + item for item in authoritative_ids}
        selected: list[LlmContextSegment] = []
        refs: list[dict[str, object]] = []
        terms = set(re.findall(r"[a-z0-9]+", question.lower()))
        for row in sorted(rows, key=lambda item: (0 if (item.safe_metadata or {}).get("approval_status") == "approved" else 1, item.relative_path)):
            metadata = row.safe_metadata or {}
            approved_metadata = metadata.get("approval_status") == "approved"
            authorized_record = row.id in canonical_authoritative_ids or row.id.removeprefix('metadata-') in authoritative_ids
            if (not approved_metadata and not authorized_record) or row.artifact_type not in self.allowed_types or (stage_id and row.stage_id != stage_id) or row.redacted:
                continue
            if not row.checksum or (not authorized_record and not metadata.get("lineage", "").startswith(run_id)):
                continue
            content = str(metadata.get("excerpt") or metadata.get("content") or row.relative_path)
            content = re.sub(r"(?i)(bearer\s+|api[_-]?key\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+", "[REDACTED]", content)
            selected.append(LlmContextSegment(segment_id=f"artifact:{row.id}", label=f"approved artifact {row.relative_path}", content=content[:8000], artifact_ref=row.id, untrusted=True))
            refs.append({"artifact_id": row.id, "checksum": row.checksum, "excerpt_locator": "safe_metadata.excerpt", "evidence_type": row.artifact_type, "proof_label": "approved_evidence_supported", "label": row.relative_path})
            if len(selected) >= limit:
                break
        return selected, refs
