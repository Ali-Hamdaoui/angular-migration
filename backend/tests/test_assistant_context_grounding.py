"""Focused grounding audit: verified-only evidence and stage provenance labels."""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.repositories.models import ArtifactMetadataModel, Base, MigrationRunModel, SourceSnapshotModel
from app.services.assistant_evidence_retrieval_service import AssistantEvidenceRetrievalService


def _scope(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'grounding.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    root = tmp_path / "artifacts"
    now = datetime.now(UTC)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-grounding", actor="alice", status="RUNNING", run_phase="STAGED_MIGRATION", phase_status="running", approval_status="approved", repair_status="not_required", state_version=5, artifact_root=str(root), created_at=now, updated_at=now))
        session.commit()

    return engine, sessions, root


def test_verified_excerpt_label_and_created_at_provenance(tmp_path):
    engine, sessions, root = _scope(tmp_path)
    store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
    stored = store.write_text_artifact("run-grounding", "03_planning/risk-report.md", "Planning risk: Angular router API requires a staged change.", ArtifactType.MARKDOWN, stage_id="planning-stage")
    with sessions() as session:
        session.add(ArtifactMetadataModel(id="metadata-" + stored.ref.artifact_id, run_id="run-grounding", stage_id="planning-stage", artifact_type="markdown", relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, immutable=True, safe_metadata={"approval_status": "approved", "lineage": "run-grounding"}, created_at=stored.ref.created_at))
        session.add(SourceSnapshotModel(id="snapshot-grounding", run_id="run-grounding", idempotency_key="snapshot-grounding", actor="worker", status="created", source_path="source", snapshot_path="snapshot", manifest_id="manifest", fingerprint="sha256:grounding", policy_version="policy", file_count=1, total_size_bytes=1, exclusions=[], git_metadata={}, artifact_ids=[stored.ref.artifact_id], state_version=5, event_sequence=2, created_at=stored.ref.created_at, updated_at=stored.ref.created_at))
        session.commit()
        segments, refs = AssistantEvidenceRetrievalService().retrieve(session, "run-grounding", "planning router risk")
    assert segments[0].label == "approved artifact excerpt 03_planning/risk-report.md [stage planning-stage]"
    assert refs[0]["proof_label"] == "approved_evidence_supported"
    assert refs[0]["checksum_verified"] is True
    assert datetime.fromisoformat(refs[0]["created_at"]).replace(tzinfo=UTC) == stored.ref.created_at
    assert "Planning risk: Angular router API" in segments[0].content
    engine.dispose()


def test_unverified_artifact_is_omitted_without_metadata_fallback(tmp_path):
    engine, sessions, root = _scope(tmp_path)
    store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
    stored = store.write_text_artifact("run-grounding", "04_validation/failed.json", "stale failure text", ArtifactType.JSON, stage_id="validation-stage")
    artifact_path = root / "04_validation" / "failed.json"
    artifact_path.write_text("corrupted after registration", encoding="utf-8")
    with sessions() as session:
        session.add(ArtifactMetadataModel(id="metadata-" + stored.ref.artifact_id, run_id="run-grounding", stage_id="validation-stage", artifact_type="json", relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, immutable=True, safe_metadata={"approval_status": "approved", "lineage": "run-grounding", "content": "UNTRUSTED_METADATA_MUST_NOT_BE_SENT"}, created_at=stored.ref.created_at))
        session.add(SourceSnapshotModel(id="snapshot-grounding-2", run_id="run-grounding", idempotency_key="snapshot-grounding-2", actor="worker", status="created", source_path="source", snapshot_path="snapshot", manifest_id="manifest", fingerprint="sha256:grounding-2", policy_version="policy", file_count=1, total_size_bytes=1, exclusions=[], git_metadata={}, artifact_ids=[stored.ref.artifact_id], state_version=5, event_sequence=3, created_at=stored.ref.created_at, updated_at=stored.ref.created_at))
        session.commit()
        retrieval = AssistantEvidenceRetrievalService()
        segments, refs = retrieval.retrieve(session, "run-grounding", "stale failure")
    assert segments == [] and refs == []
    assert {item["reason"] for item in retrieval.last_manifest["omitted_candidates"]} == {"checksum_mismatch"}
    engine.dispose()
