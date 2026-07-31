"""Focused persistence tests for idempotent transformer failure classification.

Covers pending-aware artifact metadata dedup, deterministic metadata identity,
committed-evidence replay, and replay no-op behavior (plan sections A1-A4).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.domain.transformation import FailureRoute
from app.repositories.models import (
    ArtifactMetadataModel,
    MigrationRunModel,
    MigrationStageModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.transformer_stage_service import (
    TransformerStageError,
    TransformerStageService,
    artifact_metadata_id,
)

NOW = datetime(2026, 7, 31, tzinfo=UTC)
RUN_ID = "run-1"
STAGE_ID = "stage-1"
CONTINUATION_ID = "continuation-1"
FINGERPRINT = "sha256:" + "b" * 64
EVIDENCE_PATH = f"04_workflow_state/stages/{STAGE_ID}/failures/{FINGERPRINT[7:]}.json"


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return Session


@pytest.fixture
def artifact_root(tmp_path: Path) -> str:
    return str(tmp_path / "run-root")


@pytest.fixture
def store(artifact_root: str) -> LocalFilesystemArtifactStore:
    return LocalFilesystemArtifactStore(Path(artifact_root).parent, fixed_run_root=Path(artifact_root))


@pytest.fixture
def workspace(tmp_path: Path) -> str:
    path = tmp_path / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _seed(Session, artifact_root: str) -> None:
    with Session() as session:
        session.add_all(
            [
                MigrationRunModel(
                    id=RUN_ID,
                    status="running",
                    run_phase="transformation",
                    artifact_root=artifact_root,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MigrationStageModel(
                    id=STAGE_ID,
                    run_id=RUN_ID,
                    stage_order=1,
                    status="running",
                    created_at=NOW,
                ),
                TransformationContinuationModel(
                    id=CONTINUATION_ID,
                    run_id=RUN_ID,
                    current_stage_id=STAGE_ID,
                    thread_id="thread-1",
                    status="running",
                    current_node="classify_failure",
                    g06_approval_id="g06-1",
                    plan_id="plan-1",
                    plan_checksum="plan-checksum",
                    stage_plan_id="stage-plan-1",
                    stage_plan_checksum="stage-plan-checksum",
                    idempotency_key="idempotency-key",
                    request_checksum="request-checksum",
                    state_version=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
        session.commit()


def _continuation(session) -> TransformationContinuationModel:
    return session.get(TransformationContinuationModel, CONTINUATION_ID)


def _write_evidence(store, workspace: str, artifact_root: str):
    evidence = {
        "schema_version": "transformer-failure-evidence-v1",
        "run_id": RUN_ID,
        "stage_id": STAGE_ID,
        "stage_plan_checksum": "stage-plan-checksum",
        "workspace_path": workspace,
        "workspace_fingerprint": "workspace-fingerprint",
        "artifact_root": artifact_root,
        "execution_id": "execution-1",
        "normalized_failure": {
            "error_code": "COMPILATION_FAILED",
            "exit_code": 1,
            "failure_message": "Angular compiler reported an error",
        },
        "failure_fingerprint": FINGERPRINT,
        "prior_fingerprints": [],
        "repair_policy": {},
        "forbidden_change_policy": {},
    }
    service = FailureEvidenceService()
    failure, route_artifact = service.write(evidence, FailureRoute.REPAIRABLE_SOURCE)
    context = service.write_context_pack(evidence, failure.ref.checksum)
    return failure, route_artifact, context


def _register(Session, artifacts) -> None:
    with Session() as session:
        continuation = session.get(TransformationContinuationModel, CONTINUATION_ID)
        for artifact in artifacts:
            TransformerStageService.register_artifact(session, artifact, continuation)
        session.commit()


def _expected_id(*, relative_path: str, checksum: str) -> str:
    return artifact_metadata_id(RUN_ID, STAGE_ID, ArtifactType.JSON, relative_path, checksum)


def test_register_artifact_duplicate_in_one_session_commits_exactly_one_row(db, store, artifact_root):
    _seed(db, artifact_root)
    stored = store.write_text_artifact(
        RUN_ID,
        EVIDENCE_PATH,
        '{"ok": true}',
        ArtifactType.JSON,
        stage_id=STAGE_ID,
        created_by="failure-evidence-service",
        created_at=NOW,
        input_hashes={"stage_plan": "stage-plan-checksum"},
        policy_version="transformer-failure-evidence-v1",
    )
    with db() as session:
        continuation = session.get(TransformationContinuationModel, CONTINUATION_ID)
        TransformerStageService.register_artifact(session, stored, continuation)
        TransformerStageService.register_artifact(session, stored, continuation)
        session.commit()
    with db() as session:
        rows = session.query(ArtifactMetadataModel).all()
        assert len(rows) == 1
        assert rows[0].id == _expected_id(
            relative_path=stored.ref.relative_path, checksum=stored.ref.checksum
        )


def test_register_artifact_duplicate_different_artifact_adds_separate_row(db, store, artifact_root):
    _seed(db, artifact_root)
    first = store.write_text_artifact(
        RUN_ID, EVIDENCE_PATH, '{"ok": true}', ArtifactType.JSON, stage_id=STAGE_ID, created_at=NOW
    )
    second = store.write_text_artifact(
        RUN_ID,
        f"04_workflow_state/stages/{STAGE_ID}/failures/{FINGERPRINT[7:]}-route.json",
        '{"route": "repairable_source"}',
        ArtifactType.JSON,
        stage_id=STAGE_ID,
        created_at=NOW,
    )
    with db() as session:
        continuation = session.get(TransformationContinuationModel, CONTINUATION_ID)
        TransformerStageService.register_artifact(session, first, continuation)
        TransformerStageService.register_artifact(session, first, continuation)
        TransformerStageService.register_artifact(session, second, continuation)
        session.commit()
    with db() as session:
        rows = session.query(ArtifactMetadataModel).all()
        assert len(rows) == 2
        assert {row.relative_path for row in rows} == {
            first.ref.relative_path,
            second.ref.relative_path,
        }


def test_register_artifact_deterministic_id_stable_across_sessions(db, store, artifact_root):
    _seed(db, artifact_root)
    stored = store.write_text_artifact(
        RUN_ID, EVIDENCE_PATH, '{"ok": true}', ArtifactType.JSON, stage_id=STAGE_ID, created_at=NOW
    )
    _register(db, [stored])
    with db() as session:
        first_id = session.query(ArtifactMetadataModel).one().id
    _register(db, [stored])
    with db() as session:
        rows = session.query(ArtifactMetadataModel).all()
        assert len(rows) == 1
        assert rows[0].id == first_id
    canonical = "metadata-" + hashlib.sha256(
        f"{RUN_ID}|{STAGE_ID}|{ArtifactType.JSON.value}|{stored.ref.relative_path}|{stored.ref.checksum}".encode()
    ).hexdigest()[:54]
    assert first_id == canonical
    assert len(first_id) <= 64
    assert first_id.startswith("metadata-")


def test_register_artifact_same_deterministic_id_different_payload_raises(db, store, artifact_root):
    _seed(db, artifact_root)
    stored = store.write_text_artifact(
        RUN_ID, EVIDENCE_PATH, '{"ok": true}', ArtifactType.JSON, stage_id=STAGE_ID, created_at=NOW
    )
    _register(db, [stored])
    with db() as session:
        row = session.query(ArtifactMetadataModel).one()
        row.checksum = "sha256:" + "f" * 64
        session.commit()
    with db() as session:
        continuation = session.get(TransformationContinuationModel, CONTINUATION_ID)
        with pytest.raises(TransformerStageError) as excinfo:
            TransformerStageService.register_artifact(session, stored, continuation)
        assert excinfo.value.code == "ARTIFACT_METADATA_IDENTITY_CONFLICT"
        assert "checksum" in excinfo.value.message


def test_register_artifact_committed_match_is_noop(db, store, artifact_root):
    _seed(db, artifact_root)
    stored = store.write_text_artifact(
        RUN_ID, EVIDENCE_PATH, '{"ok": true}', ArtifactType.JSON, stage_id=STAGE_ID, created_at=NOW
    )
    _register(db, [stored])
    with db() as session:
        continuation = session.get(TransformationContinuationModel, CONTINUATION_ID)
        TransformerStageService.register_artifact(session, stored, continuation)
        session.commit()
    with db() as session:
        assert session.query(ArtifactMetadataModel).count() == 1


def test_committed_evidence_returns_validated_triple(db, store, artifact_root, workspace):
    _seed(db, artifact_root)
    failure, route_artifact, context = _write_evidence(store, workspace, artifact_root)
    _register(db, [failure, route_artifact, context])
    with db() as session:
        triple = FailureEvidenceService().committed_evidence(session, _continuation(session), FINGERPRINT)
    assert triple is not None
    replayed_failure, replayed_route, replayed_context = triple
    for replayed, original in (
        (replayed_failure, failure),
        (replayed_route, route_artifact),
        (replayed_context, context),
    ):
        assert replayed.ref.artifact_id == original.ref.artifact_id
        assert replayed.ref.checksum == original.ref.checksum
        assert replayed.ref.relative_path == original.ref.relative_path
        assert replayed.ref.artifact_type == ArtifactType.JSON
        assert replayed.content == original.content
    with db() as session:
        rows = session.query(ArtifactMetadataModel).all()
        assert len(rows) == 3
        for row in rows:
            assert row.id == artifact_metadata_id(
                row.run_id, row.stage_id, ArtifactType(row.artifact_type), row.relative_path, row.checksum
            )


def test_committed_evidence_none_when_run_mismatch(db, store, artifact_root, workspace):
    _seed(db, artifact_root)
    failure, route_artifact, context = _write_evidence(store, workspace, artifact_root)
    _register(db, [failure, route_artifact, context])
    with db() as session:
        continuation = _continuation(session)
        continuation.run_id = "run-2"
        assert FailureEvidenceService().committed_evidence(session, continuation, FINGERPRINT) is None


def test_committed_evidence_none_when_stage_mismatch(db, store, artifact_root, workspace):
    _seed(db, artifact_root)
    failure, route_artifact, context = _write_evidence(store, workspace, artifact_root)
    _register(db, [failure, route_artifact, context])
    with db() as session:
        continuation = _continuation(session)
        continuation.current_stage_id = "stage-2"
        assert FailureEvidenceService().committed_evidence(session, continuation, FINGERPRINT) is None


def test_committed_evidence_none_when_artifact_type_mismatch(db, store, artifact_root, workspace):
    _seed(db, artifact_root)
    failure, route_artifact, context = _write_evidence(store, workspace, artifact_root)
    _register(db, [failure, route_artifact, context])
    with db() as session:
        rows = session.query(ArtifactMetadataModel).all()
        rows[0].artifact_type = ArtifactType.REPORT.value
        session.commit()
    with db() as session:
        assert FailureEvidenceService().committed_evidence(session, _continuation(session), FINGERPRINT) is None


def test_committed_evidence_none_when_file_missing(db, store, artifact_root, workspace):
    _seed(db, artifact_root)
    failure, route_artifact, context = _write_evidence(store, workspace, artifact_root)
    _register(db, [failure, route_artifact, context])
    Path(artifact_root, failure.ref.relative_path).unlink()
    with db() as session:
        assert FailureEvidenceService().committed_evidence(session, _continuation(session), FINGERPRINT) is None


def test_committed_evidence_none_when_file_checksum_drift(db, store, artifact_root, workspace):
    _seed(db, artifact_root)
    failure, route_artifact, context = _write_evidence(store, workspace, artifact_root)
    _register(db, [failure, route_artifact, context])
    Path(artifact_root, failure.ref.relative_path).write_text('{"tampered": true}', encoding="utf-8")
    with db() as session:
        assert FailureEvidenceService().committed_evidence(session, _continuation(session), FINGERPRINT) is None


def test_committed_evidence_none_when_duplicate_row_for_path(db, store, artifact_root, workspace):
    _seed(db, artifact_root)
    failure, route_artifact, context = _write_evidence(store, workspace, artifact_root)
    _register(db, [failure, route_artifact, context])
    with db() as session:
        row = session.query(ArtifactMetadataModel).filter_by(relative_path=failure.ref.relative_path).one()
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + "0" * 54,
                run_id=row.run_id,
                stage_id=row.stage_id,
                artifact_type=row.artifact_type,
                relative_path=row.relative_path,
                checksum=row.checksum,
                created_at=NOW,
            )
        )
        session.commit()
    with db() as session:
        assert FailureEvidenceService().committed_evidence(session, _continuation(session), FINGERPRINT) is None


def test_replay_after_commit_creates_no_rows_and_no_new_files(db, store, artifact_root, workspace):
    _seed(db, artifact_root)
    failure, route_artifact, context = _write_evidence(store, workspace, artifact_root)
    _register(db, [failure, route_artifact, context])
    files_before = sorted(
        str(path.relative_to(Path(artifact_root))) for path in Path(artifact_root).rglob("*") if path.is_file()
    )
    with db() as session:
        triple = FailureEvidenceService().committed_evidence(session, _continuation(session), FINGERPRINT)
    assert triple is not None
    _register(db, list(triple))
    with db() as session:
        assert session.query(ArtifactMetadataModel).count() == 3
    files_after = sorted(
        str(path.relative_to(Path(artifact_root))) for path in Path(artifact_root).rglob("*") if path.is_file()
    )
    assert files_after == files_before
    assert not any("__v" in name for name in files_after)
