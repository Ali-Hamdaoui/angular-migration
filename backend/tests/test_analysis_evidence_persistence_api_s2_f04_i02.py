from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.api.analysis_contracts import AnalysisCreateRequest, G04DecisionApiRequest
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.analysis import AnalysisPackage, AnalysisNarrative, AnalysisReview, G04Decision, G04DecisionResult
from app.domain.contracts import ArtifactType
from app.repositories.models import ArtifactMetadataModel, Base, G03ApprovalModel, MigrationRunModel, WorkflowEventModel
from app.repositories.session import create_database_engine
from app.services.analysis_evidence_application_service import AnalysisEvidenceApplicationService, AnalysisEvidenceError
from app.api.routes import analysis as analysis_routes
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker


NOW = datetime(2026, 7, 19, tzinfo=UTC)


class FakeAnalysisAgent:
    def __init__(self, *, failure: Exception | None = None):
        self.failure = failure
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        if self.failure:
            raise self.failure
        return AnalysisPackage(
            run_id=request.run_id,
            artifact_set_checksum=request.artifact_set_checksum,
            deterministic_input_artifacts=request.prerequisite_artifacts,
            narrative=AnalysisNarrative(
                summary="The deterministic findings require compatibility review.",
                risk_groups=[{"name": "builder", "finding_ids": ["finding-1"]}],
                unresolved_questions=["Confirm private package support"],
                evidence_confidence="high",
                recommended_next_action="Review compatibility evidence",
                deterministic_input_checksum=request.artifact_set_checksum,
            ),
            proposer_output_checksum="sha256:" + "6" * 64,
            model_provenance={"provider": "azure-openai", "role": "phase_proposer", "response_id": "response-1"},
            usage={"input_tokens": 10, "output_tokens": 15, "total_tokens": 25, "input_price_per_million": 0.25, "output_price_per_million": 2.0, "input_cost_usd": 0.0000025, "output_cost_usd": 0.00003, "total_cost_usd": 0.0000325, "pricing_version": "test-pricing-v1"},
            prompt_version="analysis_agent_v1",
            schema_version="analysis-schema-registry-v1",
            reviewer=AnalysisReview(decision="accept", notes=["Evidence is bounded."], risks=[], policy_concerns=[], confidence="high", deterministic_input_checksum=request.artifact_set_checksum, proposer_output_checksum="sha256:" + "6" * 64),
            reviewer_output_checksum="sha256:" + "7" * 64,
            reviewer_provenance={"provider": "azure-openai", "role": "phase_reviewer", "response_id": "response-2"},
            reviewer_usage={"input_tokens": 5, "output_tokens": 8, "total_tokens": 13, "input_price_per_million": 0.25, "output_price_per_million": 2.0, "input_cost_usd": 0.00000125, "output_cost_usd": 0.000016, "total_cost_usd": 0.00001725, "pricing_version": "test-pricing-v1"},
            reviewer_prompt_version="analysis_reviewer_v1",
            reviewer_schema_version="analysis-schema-registry-v1",
            workspace_fingerprint=request.workspace_fingerprint,
            plan_version=request.plan_version,
        )

    def decide_g04(self, request, package, decision):
        accepted = decision.decision in {G04Decision.APPROVE, G04Decision.APPROVE_WITH_COMMENT}
        return G04DecisionResult(run_id=request.run_id, decision=decision.decision, accepted=accepted, state_version=request.expected_state_version, gate_version=decision.gate_version, artifact_set_checksum=package.artifact_set_checksum, review_status="approved" if accepted else decision.decision.value)


def setup(tmp_path: Path, *, agent=None):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}", sqlite_wal_enabled=False)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    store = LocalFilesystemArtifactStore(tmp_path / "artifacts", fixed_run_root=tmp_path / "artifacts")
    store.ensure_run_layout("run-1")
    source = store.write_text_artifact("run-1", "02_analysis/findings.json", '{"finding":"builder"}', ArtifactType.JSON)
    with sessions.begin() as session:
        session.add(MigrationRunModel(id="run-1", status="RUNNING", run_phase="ANALYSIS", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, actor="operator", artifact_root=str(tmp_path / "artifacts"), created_at=NOW, updated_at=NOW))
        session.add(G03ApprovalModel(id="g03-1", run_id="run-1", gate_id="G03", gate_version="g03-v1", idempotency_key="g03-1", actor="operator", status="approved", decision="approved", package_checksum="sha256:" + "1" * 64, evidence_set_checksum="sha256:" + "2" * 64, qualification_status="qualified", policy_version="g03-v1", state_version=1, event_sequence=1, sandbox_fingerprint="sha256:" + "3" * 64, execution_profile_checksum="sha256:" + "4" * 64, package={}, artifact_ids=[], comment=None, created_at=NOW, updated_at=NOW))
        session.add(ArtifactMetadataModel(id="metadata-" + source.ref.artifact_id, run_id="run-1", stage_id=None, artifact_type="json", relative_path=source.ref.relative_path, checksum=source.ref.checksum, created_at=NOW))

    def scope():
        from contextlib import contextmanager
        @contextmanager
        def managed():
            session = sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        return managed()

    service = AnalysisEvidenceApplicationService(session_scope_factory=scope, analysis_agent=agent or FakeAnalysisAgent(), now_provider=lambda: NOW)
    payload = AnalysisCreateRequest(expected_state_version=1, idempotency_key="analysis-1", prerequisite_artifacts=[{"artifact_id": source.ref.artifact_id, "checksum": source.ref.checksum}], workspace_fingerprint="sha256:" + "5" * 64, correlation_id="corr-1")
    return service, payload, sessions, source


def test_analysis_persists_immutable_evidence_invocation_gate_and_events(tmp_path):
    service, payload, sessions, source = setup(tmp_path)

    result = service.generate("run-1", payload, "operator")

    assert result.status == "completed"
    assert result.gate_status == "pending"
    assert len(result.artifact_ids) == 8
    assert all(checksum.startswith("sha256:") for checksum in result.artifact_checksums.values())
    with sessions() as session:
        events = list(session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence))
        assert [event.event_type for event in events] == ["ANALYSIS_AGENT_STARTED", "ANALYSIS_AGENT_COMPLETED", "ANALYSIS_REVIEWER_STARTED", "ANALYSIS_REVIEWER_COMPLETED", "G04_CREATED"]
        assert session.query(ArtifactMetadataModel).filter(ArtifactMetadataModel.run_id == "run-1").count() == 9
        assert session.query(MigrationRunModel).one().state_version == 6
    store = LocalFilesystemArtifactStore(tmp_path / "artifacts", fixed_run_root=tmp_path / "artifacts")
    package = store.read_artifact_by_id(result.artifact_ids[-1])
    assert package.ref.checksum == result.artifact_checksums[result.artifact_ids[-1]]
    assert '{"finding":"builder"}' not in package.content
    assert "raw_content_stored" in store.read_artifact_by_id(result.artifact_ids[0]).content


def test_analysis_replays_identical_request_and_rejects_changed_payload(tmp_path):
    agent = FakeAnalysisAgent()
    service, payload, _, _ = setup(tmp_path, agent=agent)

    first = service.generate("run-1", payload, "operator")
    replay = service.generate("run-1", payload, "operator")

    assert replay.idempotent_replay is True
    assert replay.analysis_id == first.analysis_id
    assert agent.calls == 1
    with pytest.raises(AnalysisEvidenceError, match="different payload"):
        service.generate("run-1", payload.model_copy(update={"workspace_fingerprint": "sha256:" + "6" * 64}), "operator")


def test_analysis_rejects_stale_or_tampered_prerequisite_before_provider(tmp_path):
    agent = FakeAnalysisAgent()
    service, payload, _, _ = setup(tmp_path, agent=agent)
    with pytest.raises(AnalysisEvidenceError) as stale:
        service.generate("run-1", payload.model_copy(update={"expected_state_version": 2}), "operator")
    assert stale.value.code == "STALE_STATE_VERSION"
    with pytest.raises(AnalysisEvidenceError) as checksum:
        service.generate("run-1", payload.model_copy(update={"idempotency_key": "analysis-bad", "prerequisite_artifacts": [{"artifact_id": payload.prerequisite_artifacts[0].artifact_id, "checksum": "sha256:" + "a" * 64}]}), "operator")
    assert checksum.value.code == "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"
    assert agent.calls == 0


def test_g04_decision_is_append_only_bound_and_idempotent(tmp_path):
    service, payload, sessions, _ = setup(tmp_path)
    analysis = service.generate("run-1", payload, "operator")
    decision = G04DecisionApiRequest(expected_state_version=6, idempotency_key="g04-decision-1", gate_version="g04-v1", package_checksum=analysis.package_checksum, workspace_fingerprint=analysis.package["workspace_fingerprint"], plan_version=analysis.package["plan_version"], decision=G04Decision.APPROVE_WITH_COMMENT, comment="Proceed with documented risks.")

    result = service.decide_g04("run-1", decision, "operator")
    replay = service.decide_g04("run-1", decision, "operator")

    assert result.accepted is True
    assert replay.idempotent_replay is True
    with sessions() as session:
        assert session.query(WorkflowEventModel).count() == 6
        assert session.query(MigrationRunModel).one().state_version == 7
    with pytest.raises(AnalysisEvidenceError) as stale:
        service.decide_g04("run-1", decision.model_copy(update={"idempotency_key": "g04-decision-2", "package_artifact_set_checksum": "sha256:" + "a" * 64}), "operator")
    assert stale.value.code == "STALE_STATE_VERSION"


def test_analysis_dependency_failure_preserves_redacted_failure_evidence(tmp_path):
    service, payload, sessions, _ = setup(tmp_path, agent=FakeAnalysisAgent(failure=RuntimeError("secret-provider-detail")))

    result = service.generate("run-1", payload, "operator")

    assert result.status == "failed"
    assert result.error_code == "ANALYSIS_DEPENDENCY_FAILED"
    with sessions() as session:
        assert [event.event_type for event in session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence)] == ["ANALYSIS_AGENT_STARTED", "ANALYSIS_AGENT_FAILED"]
        assert session.query(WorkflowEventModel).filter(WorkflowEventModel.payload.like("%secret-provider-detail%")).count() == 0


def test_versioned_analysis_api_exposes_safe_contract_and_authenticated_actor(tmp_path):
    service, payload, _, _ = setup(tmp_path)
    app.dependency_overrides[analysis_routes.get_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/runs/run-1/analysis",
            headers={"x-authenticated-actor": "operator", "x-correlation-id": "corr-api"},
            json=payload.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(analysis_routes.get_service, None)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["gate_status"] == "pending"
    assert all(link.startswith("/api/v1/artifacts/") for link in body["artifact_links"].values())
    assert "artifact_root" not in response.text


def test_i04_invalid_prerequisite_checksum_fails_closed_without_analysis_events(tmp_path: Path):
    service, payload, sessions, source = setup(tmp_path, agent=FakeAnalysisAgent())
    invalid = AnalysisCreateRequest(
        expected_state_version=payload.expected_state_version,
        idempotency_key="analysis-invalid-checksum",
        prerequisite_artifacts=[{"artifact_id": source.ref.artifact_id, "checksum": "sha256:" + "f" * 64}],
    )

    with pytest.raises(AnalysisEvidenceError) as error:
        service.generate("run-1", invalid, "operator")

    assert error.value.code == "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"
    with sessions() as session:
        assert session.query(WorkflowEventModel).count() == 0
        assert session.query(MigrationRunModel).one().state_version == 1


def test_i04_g04_reject_decision_is_recorded_without_becoming_approval(tmp_path: Path):
    service, payload, sessions, _ = setup(tmp_path, agent=FakeAnalysisAgent())
    analysis = service.generate("run-1", payload, "operator")

    result = service.decide_g04(
        "run-1",
        G04DecisionApiRequest(
            expected_state_version=analysis.state_version,
            idempotency_key="g04-reject-verification",
            gate_version=analysis.gate_version,
            package_checksum=analysis.package_checksum,
            workspace_fingerprint=analysis.package["workspace_fingerprint"],
            plan_version=analysis.package["plan_version"],
            decision=G04Decision.REJECT,
            comment="Evidence is insufficient for acceptance.",
        ),
        "operator",
    )

    assert result.accepted is False
    assert result.status == "reject"
    with sessions() as session:
        assert session.query(MigrationRunModel).one().state_version == 7
        assert session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence).all()[-1].event_type == "G04_REJECTED"


def test_protected_progression_requires_current_approved_g04_and_rejects_stale_bindings(tmp_path: Path):
    service, payload, _, _ = setup(tmp_path, agent=FakeAnalysisAgent())
    analysis = service.generate("run-1", payload, "operator")

    with pytest.raises(AnalysisEvidenceError) as pending:
        service.require_approved_g04("run-1", expected_state_version=analysis.state_version, workspace_fingerprint=analysis.package["workspace_fingerprint"], plan_version=analysis.package["plan_version"], actor="operator")
    assert pending.value.code == "G04_APPROVAL_REQUIRED"

    decision = G04DecisionApiRequest(expected_state_version=analysis.state_version, idempotency_key="g04-progression", gate_version="g04-v1", package_checksum=analysis.package_checksum, workspace_fingerprint=analysis.package["workspace_fingerprint"], plan_version=analysis.package["plan_version"], decision=G04Decision.APPROVE)
    approved = service.decide_g04("run-1", decision, "operator")
    gate = service.require_approved_g04("run-1", expected_state_version=approved.state_version, workspace_fingerprint=analysis.package["workspace_fingerprint"], plan_version=analysis.package["plan_version"], actor="operator")
    assert gate.status == "approved"

    with pytest.raises(AnalysisEvidenceError) as stale:
        service.require_approved_g04("run-1", expected_state_version=approved.state_version, workspace_fingerprint="sha256:" + "9" * 64, plan_version=analysis.package["plan_version"], actor="operator")
    assert stale.value.code == "G04_STALE"


def test_tampered_g04_package_is_recorded_stale_and_cannot_be_decided(tmp_path: Path):
    service, payload, sessions, _ = setup(tmp_path, agent=FakeAnalysisAgent())
    analysis = service.generate("run-1", payload, "operator")
    with sessions() as session:
        gate = session.query(__import__("app.repositories.analysis_models", fromlist=["G04ApprovalModel"]).G04ApprovalModel).filter_by(run_id="run-1", status="pending").one()
        gate.package_checksum = "sha256:" + "f" * 64
        session.commit()

    with pytest.raises(AnalysisEvidenceError) as error:
        service.decide_g04("run-1", G04DecisionApiRequest(expected_state_version=analysis.state_version, idempotency_key="g04-tampered", gate_version="g04-v1", package_checksum="sha256:" + "f" * 64, workspace_fingerprint=analysis.package["workspace_fingerprint"], plan_version=analysis.package["plan_version"], decision=G04Decision.APPROVE), "operator")
    assert error.value.code == "G04_PACKAGE_INTEGRITY_FAILED"
