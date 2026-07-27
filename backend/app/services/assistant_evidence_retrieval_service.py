"""Approved, immutable, checksum-bound evidence selection for Assistant context."""

import re
from sqlalchemy import select

from app.llm_gateway import LlmContextSegment
from app.repositories.models import ArtifactMetadataModel


class AssistantEvidenceRetrievalService:
    allowed_types = frozenset({"json", "yaml", "markdown", "text_log", "command_log", "report"})

    def retrieve(self, session, run_id: str, question: str, *, stage_id: str | None = None, limit: int = 8) -> tuple[list[LlmContextSegment], list[dict[str, object]]]:
        rows = session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id, ArtifactMetadataModel.immutable.is_(True))).all()
        selected: list[LlmContextSegment] = []
        refs: list[dict[str, object]] = []
        terms = set(re.findall(r"[a-z0-9]+", question.lower()))
        for row in sorted(rows, key=lambda item: (0 if (item.safe_metadata or {}).get("approval_status") == "approved" else 1, item.relative_path)):
            metadata = row.safe_metadata or {}
            if metadata.get("approval_status") != "approved" or row.artifact_type not in self.allowed_types or (stage_id and row.stage_id != stage_id):
                continue
            if not row.checksum or not metadata.get("lineage", "").startswith(run_id):
                continue
            content = str(metadata.get("excerpt") or metadata.get("content") or row.relative_path)
            content = re.sub(r"(?i)(bearer\s+|api[_-]?key\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+", "[REDACTED]", content)
            selected.append(LlmContextSegment(segment_id=f"artifact:{row.id}", label=f"approved artifact {row.relative_path}", content=content[:8000], artifact_ref=row.id))
            refs.append({"artifact_id": row.id, "checksum": row.checksum, "excerpt_locator": "safe_metadata.excerpt", "evidence_type": row.artifact_type, "proof_label": "approved_evidence_supported", "label": row.relative_path})
            if len(selected) >= limit:
                break
        return selected, refs
