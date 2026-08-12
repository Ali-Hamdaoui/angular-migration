from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import AgentKind, ArtifactType, AssistantMessageRequestDto
from app.llm_gateway import LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, build_usage_record
from app.repositories.models import AnalysisMetadataModel, ArtifactMetadataModel, AssistantMessageModel, Base, MigrationRunModel, SourceSnapshotModel
from app.services.assistant_context_service import AssistantContextService, AssistantRequestError
from app.services.assistant_evidence_retrieval_service import AssistantEvidenceRetrievalService
from app.services.llm_evidence_application_service import build_assistant_response_contract


def _scope(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r3.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    root = tmp_path / "artifacts"
    now = datetime.now(UTC)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-r3", actor="alice", status="RUNNING", run_phase="FEASIBILITY_PLANNING", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(root), created_at=now, updated_at=now))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    return engine, scope, sessions, root


def _artifact(sessions, root: Path, artifact_id: str, content: str, *, approved=True):
    store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
    stored = store.write_text_artifact("run-r3", f"evidence/{artifact_id}.json", content, ArtifactType.JSON, created_by="test")
    with sessions() as session:
        session.add(ArtifactMetadataModel(id=f"metadata-{stored.ref.artifact_id}", run_id="run-r3", stage_id=None, artifact_type="json", relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, immutable=True, safe_metadata={"approval_status": "approved" if approved else "pending", "content": "UNTRUSTED_METADATA_MUST_NOT_BE_SENT", "lineage": "run-r3"}, created_at=stored.ref.created_at))
        session.commit()
    return stored


def _approve_snapshot(sessions, artifact_ids):
    now = datetime.now(UTC)
    with sessions() as session:
        session.add(SourceSnapshotModel(id="snapshot-r3", run_id="run-r3", idempotency_key="snapshot-r3", actor="worker", status="created", source_path="source", snapshot_path="snapshot", manifest_id="manifest", fingerprint="sha256:snapshot", policy_version="policy", file_count=1, total_size_bytes=1, exclusions=[], git_metadata={}, artifact_ids=artifact_ids, state_version=1, event_sequence=1, created_at=now, updated_at=now))
        session.commit()


def _provider_response(request, *, output, run_id="run-r3"):
    usage = build_usage_record(run_id=run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="r3-fake", input_tokens=3, output_tokens=2, input_price_per_million=0, output_price_per_million=0)
    return LlmResponse(response_id="r3-response", request_id=request.request_id, run_id=run_id, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="r3-fake", status="completed", summary="r3", structured_output=output, usage=usage, redaction=PromptRedactionResult(redacted_text="redacted", redaction_count=1), role=LlmRole.ASSISTANT, prompt_version="r3", schema_version="r3", pricing_version="test")


class ExactCitationGateway:
    def __init__(self, citation_factory=None):
        self.calls = []
        self.citation_factory = citation_factory

    def complete(self, request):
        self.calls.append(request)
        result = {"answer": "Evidence-backed answer.", "summary": "Evidence-backed answer.", "intent": "evidence_question", "capability_key": "evidence_question", "proof_label": "approved_evidence_supported", "citations": [], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
        if self.citation_factory:
            result["citations"] = [self.citation_factory(request)]
        return _provider_response(request, output=result)


def _citation_from_segment(request, segment_index=1):
    segment = request.context[segment_index]
    return {"excerpt_id": segment.segment_id, "artifact_id": segment.artifact_ref.removeprefix("excerpt-") if False else "", "checksum_sha256": "", "stage_key": "run", "locator": {"kind": "line_range", "value": "1-1"}, "proof_label": "approved_evidence_supported"}


def test_response_contract_forbids_citations_when_no_evidence_was_selected():
    contract = build_assistant_response_contract(
        intent="workflow_status",
        capability_key="workflow_status",
        selected_excerpt_ids=[],
    )
    response = {
        "answer": "Current durable state.",
        "summary": "Current durable state.",
        "intent": "workflow_status",
        "capability_key": "workflow_status",
        "proof_label": "authoritative_persisted_fact",
        "citations": [],
        "missing_information": [],
        "suggested_follow_ups": [],
        "next_step_proposals": [],
        "confidence": "high",
    }

    assert contract.model_validate(response).citations == []
    response["citations"] = [{
        "excerpt_id": "fabricated",
        "artifact_id": "fabricated",
        "checksum_sha256": "sha256:fabricated",
        "stage_key": "run",
        "locator": {"kind": "line_range", "value": "1-1"},
        "proof_label": "approved_evidence_supported",
    }]
    with pytest.raises(ValueError):
        contract.model_validate(response)


def test_response_contract_binds_each_excerpt_to_its_own_coordinates():
    refs = [
        {"excerpt_id": "excerpt-a", "artifact_id": "artifact-a", "checksum_sha256": "sha256:a", "stage_key": "run", "locator": {"kind": "line_range", "value": "1-2"}},
        {"excerpt_id": "excerpt-b", "artifact_id": "artifact-b", "checksum_sha256": "sha256:b", "stage_key": "stage", "locator": {"kind": "line_range", "value": "3-4"}},
    ]
    contract = build_assistant_response_contract(intent="evidence_question", capability_key="analysis", selected_excerpt_ids=["excerpt-a", "excerpt-b"], selected_citations=refs)
    response = {"answer": "answer", "summary": "summary", "intent": "evidence_question", "capability_key": "analysis", "proof_label": "approved_evidence_supported", "citations": [{**refs[0], "artifact_id": "artifact-b", "proof_label": "approved_evidence_supported"}], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
    with pytest.raises(ValueError):
        contract.model_validate(response)


def test_non_evidence_capability_forbids_optional_citations():
    ref = {"excerpt_id": "excerpt-plan", "artifact_id": "artifact-plan", "checksum_sha256": "sha256:plan", "stage_key": "planning", "locator": {"kind": "line_range", "value": "1-2"}}
    contract = build_assistant_response_contract(intent="planning_explanation", capability_key="planning", selected_excerpt_ids=["excerpt-plan"], selected_citations=[ref])
    response = {"answer": "answer", "summary": "summary", "intent": "planning_explanation", "capability_key": "planning", "proof_label": "approved_evidence_supported", "citations": [{**ref, "proof_label": "approved_evidence_supported"}], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
    with pytest.raises(ValueError):
        contract.model_validate(response)


def test_reviewer_accepted_analysis_artifacts_are_authorized_at_g04(tmp_path):
    engine, scope, sessions, root = _scope(tmp_path)
    stored = _artifact(sessions, root, "analysis", "analysis discovered a current migration risk", approved=False)
    now = datetime.now(UTC)
    with sessions() as session:
        session.add(AnalysisMetadataModel(id="analysis-r3", run_id="run-r3", idempotency_key="analysis", request_checksum="sha256:req", actor="worker", status="completed", artifact_set_checksum="sha256:set", prerequisite_artifact_ids=[], artifact_ids=[stored.ref.artifact_id], artifact_checksums={stored.ref.artifact_id: stored.ref.checksum}, package={"review_status": "accepted"}, state_version=2, event_sequence=2, created_at=now, updated_at=now))
        session.commit()
    with scope() as session:
        segments, refs = AssistantEvidenceRetrievalService().retrieve(session, "run-r3", "analysis discovered risk")
    assert segments and refs[0]["artifact_id"] == stored.ref.artifact_id
    engine.dispose()


def test_retrieval_prioritizes_phase_relevant_artifact_paths(tmp_path):
    engine, scope, sessions, root = _scope(tmp_path)
    analysis = _artifact(sessions, root, "analysis", "shared migration evidence", approved=True)
    planning = _artifact(sessions, root, "planning", "shared migration evidence for ordered stages", approved=True)
    with sessions() as session:
        for row in session.query(ArtifactMetadataModel).all():
            if row.id.endswith(planning.ref.artifact_id):
                row.relative_path = "03_planning/planning-package.json"
            elif row.id.endswith(analysis.ref.artifact_id):
                row.relative_path = "02_analysis/analysis-package.json"
        session.commit()
    _approve_snapshot(sessions, [analysis.ref.artifact_id, planning.ref.artifact_id])
    with scope() as session:
        _, refs = AssistantEvidenceRetrievalService().retrieve(session, "run-r3", "What is the migration plan?")
    assert refs[0]["artifact_id"] == planning.ref.artifact_id
    engine.dispose()


def test_retrieval_reads_store_content_and_excludes_metadata_content(tmp_path):
    engine, scope, sessions, root = _scope(tmp_path)
    stored = _artifact(sessions, root, "a", "approved store content", approved=True)
    _approve_snapshot(sessions, [stored.ref.artifact_id])
    with scope() as session:
        segments, refs = AssistantEvidenceRetrievalService().retrieve(session, "run-r3", "approved store content")
    assert segments and segments[0].content == "approved store content"
    assert "UNTRUSTED_METADATA_MUST_NOT_BE_SENT" not in segments[0].content
    assert refs[0]["artifact_id"] == stored.ref.artifact_id
    assert refs[0]["excerpt_id"].startswith("excerpt-")
    engine.dispose()


def test_checksum_mismatch_is_omitted_before_provider_context(tmp_path):
    engine, scope, sessions, root = _scope(tmp_path)
    stored = _artifact(sessions, root, "corrupt", "approved content", approved=True)
    _approve_snapshot(sessions, [stored.ref.artifact_id])
    artifact_path = root / "evidence" / "corrupt.json"
    artifact_path.write_text("corrupted after registration", encoding="utf-8")
    with scope() as session:
        retrieval = AssistantEvidenceRetrievalService()
        segments, refs = retrieval.retrieve(session, "run-r3", "approved content")
    assert segments == [] and refs == []
    assert {item["reason"] for item in retrieval.last_manifest["omitted_candidates"]} == {"checksum_mismatch"}
    engine.dispose()


def test_exact_selected_citation_round_trips_and_projection_cannot_overwrite(tmp_path):
    engine, scope, sessions, root = _scope(tmp_path)
    a = _artifact(sessions, root, "a", "evidence for the current migration state", approved=True)
    b = _artifact(sessions, root, "b", "unrelated projection B", approved=True)
    _approve_snapshot(sessions, [a.ref.artifact_id, b.ref.artifact_id])
    with scope() as session:
        retrieval = AssistantEvidenceRetrievalService()
        _, refs = retrieval.retrieve(session, "run-r3", "evidence question selected A")
    selected = next(item for item in refs if item["artifact_id"] == a.ref.artifact_id)

    class Gateway:
        def __init__(self): self.calls = []
        def complete(self, request):
            self.calls.append(request)
            output = {"answer": "Evidence-backed answer.", "summary": "Evidence-backed answer.", "intent": "evidence_question", "capability_key": "analysis", "proof_label": "approved_evidence_supported", "citations": [{"excerpt_id": selected["excerpt_id"], "artifact_id": selected["artifact_id"], "checksum_sha256": selected["checksum_sha256"], "stage_key": selected["stage_key"], "locator": selected["locator"], "proof_label": selected["proof_label"]}], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
            return _provider_response(request, output=output)

    gateway = Gateway()
    result = AssistantContextService(session_scope_factory=scope, gateway=gateway).answer(AssistantMessageRequestDto(run_id="run-r3", message="What evidence supports this?", idempotency_key="exact"), actor="alice")
    assert [item["excerpt_id"] for item in result.citations] == [selected["excerpt_id"]]
    assert [item.excerpt_id for item in result.evidence_references] == [selected["excerpt_id"]]
    history = AssistantContextService(session_scope_factory=scope, gateway=gateway).history("run-r3", result.conversation_id, actor="alice")
    assert history.messages[-1].citations == result.citations
    with sessions() as session:
        row = session.query(AssistantMessageModel).filter_by(message_id=result.message_id).one()
        assert [item["excerpt_id"] for item in row.evidence] == [selected["excerpt_id"]]
    assert selected["artifact_id"] != b.ref.artifact_id
    engine.dispose()


def test_unselected_excerpt_is_invalid_citation_with_correlation(tmp_path):
    engine, scope, sessions, root = _scope(tmp_path)
    a = _artifact(sessions, root, "a", "selected evidence question", approved=True)
    b = _artifact(sessions, root, "b", "different artifact", approved=True)
    _approve_snapshot(sessions, [a.ref.artifact_id, b.ref.artifact_id])
    with scope() as session:
        refs = AssistantEvidenceRetrievalService()
        _, selected_refs = refs.retrieve(session, "run-r3", "selected evidence question")
    b_ref = {"excerpt_id": "excerpt-not-selected", "artifact_id": b.ref.artifact_id, "checksum_sha256": b.ref.checksum, "stage_key": "run", "locator": {"kind": "line_range", "value": "1-1"}, "proof_label": "approved_evidence_supported"}

    class Gateway:
        def complete(self, request):
            output = {"answer": "bad", "summary": "bad", "intent": "evidence_question", "capability_key": "analysis", "proof_label": "approved_evidence_supported", "citations": [b_ref], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
            return _provider_response(request, output=output)

    try:
        AssistantContextService(session_scope_factory=scope, gateway=Gateway()).answer(AssistantMessageRequestDto(run_id="run-r3", message="What evidence supports this?", idempotency_key="unselected"), actor="alice")
    except AssistantRequestError as error:
        assert error.code == "assistant_invalid_citation"
    else:
        raise AssertionError("unselected citation was accepted")
    with sessions() as session:
        row = session.query(AssistantMessageModel).filter_by(status="failed").one()
        assert row.status == "failed" and row.correlation_id
    assert selected_refs
    engine.dispose()


def test_provider_answer_and_validated_citation_are_preserved_without_normalization(tmp_path):
    engine, scope, sessions, root = _scope(tmp_path)
    a = _artifact(sessions, root, "a", "evidence for the current migration state", approved=True)
    _approve_snapshot(sessions, [a.ref.artifact_id])
    with scope() as session:
        retrieval = AssistantEvidenceRetrievalService()
        _, refs = retrieval.retrieve(session, "run-r3", "What approved evidence supports this?")
    selected = refs[0]

    class Gateway:
        def complete(self, request):
            output = {"answer": "unknown", "summary": "unknown", "intent": "evidence_question", "capability_key": "analysis", "proof_label": "approved_evidence_supported", "citations": [{"excerpt_id": selected["excerpt_id"], "artifact_id": selected["artifact_id"], "checksum_sha256": selected["checksum_sha256"], "stage_key": selected["stage_key"], "locator": selected["locator"], "proof_label": selected["proof_label"]}], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
            return _provider_response(request, output=output)

    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    projection = {"phase": "Validation", "stage": "runtime", "status": "FAILED", "gate": "G02", "gate_status": "approved", "blocker": "NO_COMPATIBLE_RUNTIME_PROFILE", "waiting_reason": "unknown", "failure_reason": "unknown", "next_action": "Install the approved runtime.", "completed_phases": ["Source snapshot"], "remaining_phases": ["Validation"], "state_version": 1, "events": [], "evidence": [], "usage": [], "duration_seconds": 1, "operational_statistics": {}}
    service._run = lambda _run_id: object()
    service._projection = lambda _run: projection
    result = service.answer(AssistantMessageRequestDto(run_id="run-r3", message="What approved evidence supports this?", idempotency_key="reconstruct"), actor="alice")
    assert result.proof_label == "approved_evidence_supported"
    assert [item["excerpt_id"] for item in result.citations] == [selected["excerpt_id"]]
    assert result.answer == "unknown"
    with sessions() as session:
        row = session.query(AssistantMessageModel).filter_by(message_id=result.message_id).one()
        assert [item["excerpt_id"] for item in row.evidence] == [selected["excerpt_id"]]
    engine.dispose()
