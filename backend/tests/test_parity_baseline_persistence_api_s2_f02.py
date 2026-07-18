import json
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.parity_baseline_contracts import ParityBaselineCaptureRequest
from app.repositories.models import ArtifactMetadataModel, Base, G03ApprovalModel, MigrationRunModel, WorkflowEventModel
from app.repositories.parity_baseline_models import ParityBaselineEvidenceModel
from app.services.parity_baseline_evidence_application_service import ParityBaselineEvidenceApplicationService

NOW = datetime(2026, 7, 18, tzinfo=UTC)


def fixture(tmp_path):
    workspace = tmp_path / "snapshot"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "angular.json").write_text(json.dumps({"projects": {"app": {"sourceRoot": "src"}}}))
    (workspace / "src" / "app.routes.ts").write_text("export const routes=[{path:'home'}]")
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as s:
        s.add(
            MigrationRunModel(
                id="run-1",
                status="CREATED",
                run_phase="DISCOVERY_BASELINE",
                phase_status="running",
                approval_status="approved",
                repair_status="not_required",
                state_version=1,
                artifact_root=str(tmp_path / "artifacts"),
                workspace_aliases={"SOURCE_SNAPSHOT": str(workspace)},
                created_at=NOW,
                updated_at=NOW,
            )
        )
        s.add(
            ArtifactMetadataModel(
                id="metadata-baseline",
                run_id="run-1",
                stage_id=None,
                artifact_type="json",
                relative_path="baseline.json",
                checksum="sha256:baseline",
                created_at=NOW,
            )
        )
        s.add(
            G03ApprovalModel(
                id="g03",
                run_id="run-1",
                gate_id="G03",
                gate_version="v1",
                idempotency_key="g03",
                actor="operator",
                status="approved",
                decision="approved",
                package_checksum="sha256:p",
                evidence_set_checksum="sha256:e",
                qualification_status="qualified",
                policy_version="v1",
                state_version=1,
                event_sequence=1,
                sandbox_fingerprint="sha256:s",
                execution_profile_checksum="sha256:r",
                package={},
                artifact_ids=[],
                comment=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        s.commit()

    @contextmanager
    def scope():
        with sessions() as s:
            yield s
            s.commit()

    return scope, sessions


def request(key="parity-1", checksum="sha256:baseline"):
    return ParityBaselineCaptureRequest(
        expected_state_version=1,
        idempotency_key=key,
        actor="operator",
        prerequisite_artifact_ids=["baseline"],
        prerequisite_artifact_checksums={"baseline": checksum},
    )


def test_persists_immutable_artifacts_events_and_idempotent_replay(tmp_path):
    scope, sessions = fixture(tmp_path)
    service = ParityBaselineEvidenceApplicationService(scope=scope, now_provider=lambda: NOW)
    result = service.capture("run-1", request())
    assert service.capture("run-1", request()).idempotent_replay
    with sessions() as s:
        assert s.get(ParityBaselineEvidenceModel, result.evidence_id) is not None
        assert len(result.artifact_ids) == 5 and all(
            value.startswith("sha256:") for value in result.artifact_checksums.values()
        )
        assert [
            event.event_type for event in s.scalars(select(WorkflowEventModel).order_by(WorkflowEventModel.sequence))
        ] == ["PARITY_BASELINE_STARTED", "PARITY_BASELINE_COMPLETED"]


def test_rejects_checksum_mismatch_without_event(tmp_path):
    scope, sessions = fixture(tmp_path)
    service = ParityBaselineEvidenceApplicationService(scope=scope, now_provider=lambda: NOW)
    try:
        service.capture("run-1", request(checksum="sha256:bad"))
    except Exception as error:
        assert error.code == "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"
    with sessions() as s:
        assert s.scalar(select(ParityBaselineEvidenceModel)) is None and s.scalar(select(WorkflowEventModel)) is None
