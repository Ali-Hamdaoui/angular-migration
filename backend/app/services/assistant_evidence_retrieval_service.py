"""Select bounded evidence excerpts from immutable, run-owned artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.artifact_store import ArtifactStoreError, LocalFilesystemArtifactStore
from app.core.config import get_settings
from app.llm_gateway import LlmContextSegment
from app.repositories.models import (
    ArtifactMetadataModel,
    ExecutionProfileModel,
    G02ApprovalModel,
    MigrationRunModel,
    SourceSnapshotModel,
)

_SECRET = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[:=]\s*|password\s*[:=]\s*|secret\s*[:=]\s*)[^\s,;]+")
_PATH = re.compile(r"(?i)([a-z]:\\|/home/|/Users/|/workspace/)[^\s,;]+")


class AssistantEvidenceRetrievalService:
    allowed_types = frozenset({"json", "yaml", "markdown", "text_log", "command_log", "report"})
    omission_reasons = frozenset({
        "not_approved", "not_authorized", "wrong_run", "wrong_stage", "type_not_allowed",
        "not_immutable", "superseded", "invalid_lineage", "checksum_mismatch",
        "empty_after_redaction", "not_relevant", "selection_limit",
    })

    def __init__(self, *, artifact_store_factory=None) -> None:
        self._artifact_store_factory = artifact_store_factory
        self.last_manifest: dict[str, object] = {}

    @staticmethod
    def excerpt_id(*, artifact_id: str, checksum: str, stage_key: str, locator: dict[str, str]) -> str:
        coordinates = "|".join((artifact_id, checksum, stage_key, locator["kind"], locator["value"]))
        return "excerpt-" + hashlib.sha256(coordinates.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _artifact_id(row: ArtifactMetadataModel) -> str:
        return row.id.removeprefix("metadata-")

    @staticmethod
    def _redact(text: str) -> str:
        return _PATH.sub("[REDACTED_PATH]", _SECRET.sub("[REDACTED]", text))

    @staticmethod
    def _terms(value: str) -> set[str]:
        return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 2}

    @staticmethod
    def _authorized_ids(session, run_id: str) -> set[str]:
        authorized: set[str] = set()
        snapshot = session.scalar(select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run_id).order_by(SourceSnapshotModel.created_at.desc()))
        g02 = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.updated_at.desc()))
        profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))
        if snapshot is not None and snapshot.status == "created":
            authorized.update(snapshot.artifact_ids or [])
        if g02 is not None and g02.status == "approved":
            authorized.update(g02.artifact_ids or [])
        if profile is not None:
            authorized.update(profile.artifact_ids or [])
        return authorized

    def _store(self, session, run_id: str) -> LocalFilesystemArtifactStore | None:
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            return None
        root = Path(run.artifact_root or get_settings().artifact_root)
        return self._artifact_store_factory(root) if self._artifact_store_factory else LocalFilesystemArtifactStore(root, fixed_run_root=root)

    def retrieve(self, session, run_id: str, question: str, *, stage_id: str | None = None, limit: int = 8) -> tuple[list[LlmContextSegment], list[dict[str, object]]]:
        rows = session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id, ArtifactMetadataModel.immutable.is_(True))).all()
        authorized = self._authorized_ids(session, run_id)
        canonical_authorized = authorized | {"metadata-" + item for item in authorized}
        store = self._store(session, run_id)
        candidates = [row.id for row in rows]
        selected: list[LlmContextSegment] = []
        refs: list[dict[str, object]] = []
        omitted: list[dict[str, str]] = []
        terms = self._terms(question)
        for row in sorted(rows, key=lambda item: (item.relative_path, item.id)):
            metadata = row.safe_metadata or {}
            artifact_id = self._artifact_id(row)
            authorized_record = artifact_id in authorized or row.id in canonical_authorized
            reason: str | None = None
            if row.run_id != run_id:
                reason = "wrong_run"
            elif row.artifact_type not in self.allowed_types:
                reason = "type_not_allowed"
            elif stage_id and row.stage_id != stage_id:
                reason = "wrong_stage"
            elif not row.immutable:
                reason = "not_immutable"
            elif metadata.get("superseded") is True or metadata.get("rejected") is True:
                reason = "superseded"
            elif not authorized_record and metadata.get("approval_status") not in {"approved", "approved_with_comment"}:
                reason = "not_approved"
            elif not authorized_record and not str(metadata.get("lineage", "")).startswith(run_id):
                reason = "invalid_lineage"
            if reason:
                omitted.append({"artifact_id": row.id, "reason": reason})
                continue

            checksum_verified = False
            content: str | None = None
            if store is not None:
                try:
                    stored = store.read_artifact_by_id(artifact_id)
                    content = stored.content
                    checksum_verified = stored.ref.run_id == run_id and stored.ref.checksum == row.checksum
                except (ArtifactStoreError, FileNotFoundError, OSError, ValueError):
                    content = None
            if content is None or not checksum_verified:
                # Fail closed: unverified bytes or untrusted metadata content
                # must never reach the provider as evidence.
                omitted.append({"artifact_id": row.id, "reason": "checksum_mismatch"})
                continue
            content = self._redact(content)
            if not content.strip():
                omitted.append({"artifact_id": row.id, "reason": "empty_after_redaction"})
                continue
            searchable = " ".join((row.relative_path, row.artifact_type, json.dumps(metadata, sort_keys=True), content[:4000]))
            if terms and not (terms & self._terms(searchable)):
                omitted.append({"artifact_id": row.id, "reason": "not_relevant"})
                continue
            lines = content.splitlines() or [content]
            bounded_lines = lines[:200]
            bounded = "\n".join(bounded_lines)[:8000]
            locator = {"kind": "line_range", "value": f"1-{len(bounded_lines)}"}
            stage_key = row.stage_id or (stored.ref.stage_id if checksum_verified else None) or "run"
            selected_id = self.excerpt_id(artifact_id=artifact_id, checksum=row.checksum, stage_key=stage_key, locator=locator)
            safe_label = _PATH.sub("[REDACTED_PATH]", row.relative_path)
            created_at = row.created_at.isoformat() if isinstance(getattr(row, "created_at", None), datetime) else None
            ref = {
                "excerpt_id": selected_id, "artifact_id": artifact_id, "checksum_sha256": row.checksum,
                "checksum": row.checksum, "stage_key": stage_key, "stage_id": row.stage_id,
                "locator": locator, "excerpt_locator": locator, "proof_label": "approved_evidence_supported",
                "checksum_verified": checksum_verified, "text": bounded, "label": safe_label, "evidence_type": row.artifact_type,
                "created_at": created_at,
            }
            selected.append(LlmContextSegment(segment_id=selected_id, label=f"approved artifact excerpt {safe_label} [stage {stage_key}] [created {created_at or 'unavailable'}]", content=bounded, artifact_ref=selected_id, untrusted=True))
            refs.append(ref)
            if len(selected) >= limit:
                selected_ids = {item["artifact_id"] for item in refs}
                omitted_ids = {item["artifact_id"] for item in omitted}
                for remaining in rows:
                    if remaining.id not in selected_ids and remaining.id not in omitted_ids:
                        omitted.append({"artifact_id": remaining.id, "reason": "selection_limit"})
                break
        self.last_manifest = {
            "schema_version": "assistant-evidence-selection-v1", "run_id": run_id,
            "candidate_artifact_ids": candidates, "selected_excerpt_ids": [item["excerpt_id"] for item in refs],
            "selected_artifact_ids": [item["artifact_id"] for item in refs],
            "verified_checksums": {item["artifact_id"]: item["checksum_sha256"] for item in refs if item["checksum_verified"]},
            "locators": {item["excerpt_id"]: item["locator"] for item in refs},
            "omitted_candidates": omitted, "truncated_excerpt_ids": [], "redaction_status": "redacted_before_provider",
        }
        return selected, refs
