import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.llm_contracts import LlmInvocationResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import AgentKind, ArtifactType, AssistantMessageRequestDto
from app.llm_gateway import (
    LlmContextSegment,
    LlmResponse,
    LlmRole,
    LlmTaskType,
    PromptRedactionResult,
    build_usage_record,
)
from app.repositories.models import (
    ArtifactMetadataModel,
    AssistantMessageModel,
    Base,
    MigrationRunModel,
    SourceSnapshotModel,
)
from app.services.assistant_context_budget import (
    ANSWER_TARGETS,
    ConservativeUtf8Tokenizer,
    ContextBudgetExceeded,
    prepare_assistant_request,
)
from app.services.assistant_context_service import AssistantContextService, AssistantRequestError
from app.services.assistant_evidence_retrieval_service import AssistantEvidenceRetrievalService
from app.services.llm_evidence_application_service import LlmEvidenceApplicationService


class CountingTokenizer:
    strategy_key = "test_exact"
    strategy_version = "1"
    deployment_or_model = "test-model"

    def count_text(self, text: str) -> int:
        return len(text)

    def count_final_request(self, serialized_request: str) -> int:
        return len(serialized_request)


def _build(question="status", segments=None, mode="concise"):
    return prepare_assistant_request(
        policy="policy",
        schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        question=question,
        segments=segments or [LlmContextSegment(segment_id="projection", label="projection", content="authoritative")],
        answer_mode=mode,
        tokenizer=CountingTokenizer(),
    )


def test_final_count_changes_for_question_and_schema_without_context_change():
    base = _build()
    longer_question = _build(question="status " + "question " * 100)
    larger_schema = prepare_assistant_request(
        policy="policy",
        schema={"type": "object", "description": "schema " * 100},
        question="status",
        segments=[LlmContextSegment(segment_id="projection", label="projection", content="authoritative")],
        tokenizer=CountingTokenizer(),
    )
    assert longer_question.final_input_tokens > base.final_input_tokens
    assert larger_schema.final_input_tokens > base.final_input_tokens


def test_final_request_is_repeatedly_identical_and_manifest_is_sanitized():
    segments = [
        LlmContextSegment(segment_id="projection", label="projection", content="state"),
        LlmContextSegment(segment_id="excerpt-a", label="approved evidence", content="evidence"),
        LlmContextSegment(segment_id="history", label="history", content="prior answer"),
    ]
    first, second = _build(segments=segments), _build(segments=segments)
    assert first.serialized_input == second.serialized_input
    assert first.manifest == second.manifest
    assert "state" not in str(first.manifest)
    assert first.manifest["context_budget"]["tokenizer_strategy"] == "test_exact"


def test_duplicate_and_optional_items_are_trimmed_deterministically():
    segments = [
        LlmContextSegment(segment_id="projection", label="projection", content="state"),
        LlmContextSegment(segment_id="excerpt-a", label="approved evidence", content="same"),
        LlmContextSegment(segment_id="excerpt-duplicate", label="approved evidence", content="same"),
        LlmContextSegment(segment_id="history", label="history", content="old " * 20_000),
    ]
    prepared = _build(segments=segments)
    assert "excerpt-duplicate" in prepared.manifest["omitted_item_ids"]
    assert prepared.manifest["omission_reasons"]["excerpt-duplicate"] == "exact_duplicate"
    assert prepared.final_input_tokens + prepared.safety_reserve_tokens <= prepared.hard_input_limit


def test_mandatory_content_failure_is_fail_closed():
    try:
        _build(question="q" * 50_000, segments=[LlmContextSegment(segment_id="projection", label="projection", content="state")])
    except ContextBudgetExceeded as error:
        assert error.code == "assistant_context_budget_exceeded"
    else:
        raise AssertionError("mandatory oversized package must fail closed")


def test_adaptive_targets_are_distinct_and_hard_cap_is_separate():
    prepared = [_build(mode=mode) for mode in ("concise", "detailed", "deep")]
    assert [item.adaptive_answer_target for item in prepared] == [ANSWER_TARGETS["concise"], ANSWER_TARGETS["detailed"], ANSWER_TARGETS["deep"]]
    assert {item.adaptive_answer_target for item in prepared} == {2000, 6000, 20000}
    assert all(item.hard_output_cap == 20_000 for item in prepared)
    assert all(item.manifest["context_budget"]["hard_output_cap"] == 20_000 for item in prepared)


def test_conservative_fallback_is_named_and_never_smaller_than_utf8():
    strategy = ConservativeUtf8Tokenizer()
    corpus = ["ascii", "é", "中文", "emoji 😀", "line\n" * 100]
    assert strategy.strategy_key == "conservative_utf8_upper_bound"
    assert all(strategy.count_text(value) >= len(value) for value in corpus)


def _proof_scope(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'question-proof.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-question-proof", actor="owner", status="RUNNING", run_phase="FEASIBILITY_PLANNING", phase_status="running", state_version=4, created_at=now, updated_at=now))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    return engine, scope


class _QuestionCaptureGateway:
    def __init__(self):
        self.calls = []

    def complete(self, request):
        self.calls.append(request)
        output = {"answer": "In progress.", "summary": "In progress.", "intent": "workflow_status", "capability_key": "workflow_status", "proof_label": "authoritative_persisted_fact", "citations": [], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
        usage = build_usage_record(run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="question-proof", input_tokens=11, output_tokens=7, input_price_per_million=0, output_price_per_million=0)
        return LlmResponse(response_id="question-proof-response", request_id=request.request_id, run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="question-proof", status="completed", summary="proof", structured_output=output, usage=usage, redaction=PromptRedactionResult(redacted_text="redacted", redaction_count=0), role=LlmRole.ASSISTANT, prompt_version="proof", schema_version="proof", pricing_version="proof")


def test_complete_question_is_preserved_through_real_assistant_pipeline(tmp_path):
    engine, scope = _proof_scope(tmp_path)
    gateway = _QuestionCaptureGateway()
    invocation = LlmEvidenceApplicationService(session_scope_factory=scope, gateway=gateway)
    question = "Where is the migration now? " + ("distinctive-question-token " * 80)
    expected_hash = hashlib.sha256(question.encode()).hexdigest()
    service = AssistantContextService(session_scope_factory=scope, invocation_service=invocation)

    service.answer(AssistantMessageRequestDto(run_id="run-question-proof", message=question, request_id="question-preserve", idempotency_key="question-preserve"), actor="owner", correlation_id="question-correlation")

    prepared = gateway.calls[0].prepared_input
    prepared_question = json.loads(prepared["serialized_input"])["question"]
    assert hashlib.sha256(prepared_question.encode()).hexdigest() == expected_hash
    assert len(prepared_question) == len(question)
    engine.dispose()


def test_complete_mandatory_question_overflow_fails_before_provider(tmp_path):
    engine, scope = _proof_scope(tmp_path)
    gateway = _QuestionCaptureGateway()
    invocation = LlmEvidenceApplicationService(session_scope_factory=scope, gateway=gateway)
    question = "Where is the migration now? " + ("mandatory-question-token " * 5000)
    service = AssistantContextService(session_scope_factory=scope, invocation_service=invocation)

    try:
        service.answer(AssistantMessageRequestDto(run_id="run-question-proof", message=question, request_id="question-overflow", idempotency_key="question-overflow"), actor="owner", correlation_id="overflow-correlation")
    except AssistantRequestError as error:
        assert error.code == "assistant_context_budget_exceeded"
    else:
        raise AssertionError("mandatory question overflow must fail closed")
    with scope() as session:
        failed = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == "run-question-proof", AssistantMessageModel.role == "assistant").order_by(AssistantMessageModel.created_at.desc()))
    assert gateway.calls == []
    assert failed is not None and failed.status == "failed"
    assert "mandatory-question-token" not in str(failed.input_manifest)
    engine.dispose()


def _evidence_proof_scope(tmp_path, *, artifact_count=1):
    engine, scope = _proof_scope(tmp_path)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    root = tmp_path / "artifacts"
    now = datetime.now(UTC)
    with sessions() as session:
        session.get(MigrationRunModel, "run-question-proof").artifact_root = str(root)
        session.commit()
    store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
    artifact_ids = []
    for index in range(artifact_count):
        content = f"approved evidence for migration status {index} " + ("evidence " * 1200 if artifact_count > 1 else "evidence")
        stored = store.write_text_artifact("run-question-proof", f"evidence/{index}.json", content, ArtifactType.JSON, created_by="proof")
        artifact_ids.append(stored.ref.artifact_id)
        with sessions() as session:
            session.add(ArtifactMetadataModel(id="metadata-" + stored.ref.artifact_id, run_id="run-question-proof", stage_id=None, artifact_type="json", relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, immutable=True, safe_metadata={"approval_status": "approved", "lineage": "run-question-proof"}, created_at=stored.ref.created_at))
            session.commit()
    with sessions() as session:
        session.add(SourceSnapshotModel(id="snapshot-question-proof", run_id="run-question-proof", idempotency_key="snapshot-question-proof", actor="owner", status="created", source_path="source", snapshot_path="snapshot", manifest_id="manifest", fingerprint="sha256:question-proof", policy_version="proof", file_count=artifact_count, total_size_bytes=1, exclusions=[], git_metadata={}, artifact_ids=artifact_ids, state_version=1, event_sequence=1, created_at=now, updated_at=now))
        session.commit()
    return engine, scope


class _EvidenceCaptureGateway(_QuestionCaptureGateway):
    def __init__(self, reference):
        super().__init__()
        self.reference = reference

    def complete(self, request):
        self.calls.append(request)
        ref = self.reference
        output = {"answer": "Evidence-backed answer.", "summary": "Evidence-backed.", "intent": "evidence_question", "capability_key": "analysis", "proof_label": "approved_evidence_supported", "citations": [{key: ref[key] for key in ("excerpt_id", "artifact_id", "checksum_sha256", "stage_key", "locator", "proof_label")}], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
        usage = build_usage_record(run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="evidence-proof", input_tokens=11, output_tokens=7, input_price_per_million=0, output_price_per_million=0)
        return LlmResponse(response_id="evidence-proof-response", request_id=request.request_id, run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="evidence-proof", status="completed", summary="proof", structured_output=output, usage=usage, redaction=PromptRedactionResult(redacted_text="redacted", redaction_count=0), role=LlmRole.ASSISTANT, prompt_version="proof", schema_version="proof", pricing_version="proof")


def _evidence_ref_and_selection(scope, service, question):
    with scope() as session:
        segments, refs = AssistantEvidenceRetrievalService().retrieve(session, "run-question-proof", question)
    projection = service._projection(service._run("run-question-proof"))
    prepared = prepare_assistant_request(policy="Answer only from the authoritative workflow projection. Do not infer unavailable fields or perform mutations.", schema=service._invocations._registry().json_schema("assistant-response-v1"), question=question, segments=[LlmContextSegment(segment_id="projection", label="projection", content=json.dumps(projection, sort_keys=True)), *segments, LlmContextSegment(segment_id="history", label="history", content="[]")])
    selected = {item["excerpt_id"] for item in refs if item["excerpt_id"] in prepared.manifest["selected_item_ids"]}
    omitted = {item["excerpt_id"] for item in refs if item["excerpt_id"] in prepared.manifest["omitted_item_ids"]}
    return refs, selected, omitted


def test_retained_r3_excerpt_is_validated_through_assistant_pipeline(tmp_path):
    engine, scope = _evidence_proof_scope(tmp_path)
    invocation = LlmEvidenceApplicationService(session_scope_factory=scope)
    service = AssistantContextService(session_scope_factory=scope, invocation_service=invocation)
    question = "What evidence supports the migration?"
    refs, selected, _ = _evidence_ref_and_selection(scope, service, question)
    reference = next(item for item in refs if item["excerpt_id"] in selected)
    gateway = _EvidenceCaptureGateway(reference)
    service = AssistantContextService(session_scope_factory=scope, invocation_service=LlmEvidenceApplicationService(session_scope_factory=scope, gateway=gateway))
    result = service.answer(AssistantMessageRequestDto(run_id="run-question-proof", message=question, request_id="evidence-retained", idempotency_key="evidence-retained"), actor="owner", correlation_id="evidence-retained-correlation")
    assert result.citations and result.citations[0]["excerpt_id"] == reference["excerpt_id"]
    assert reference["excerpt_id"] in {item.segment_id for item in gateway.calls[0].context}
    engine.dispose()


def test_omitted_r3_excerpt_is_rejected_through_assistant_pipeline(tmp_path):
    engine, scope = _evidence_proof_scope(tmp_path, artifact_count=8)
    invocation = LlmEvidenceApplicationService(session_scope_factory=scope)
    service = AssistantContextService(session_scope_factory=scope, invocation_service=invocation)
    question = "What evidence supports the migration?"
    refs, _, omitted = _evidence_ref_and_selection(scope, service, question)
    assert omitted
    reference = next(item for item in refs if item["excerpt_id"] in omitted)
    gateway = _EvidenceCaptureGateway(reference)
    service = AssistantContextService(session_scope_factory=scope, invocation_service=LlmEvidenceApplicationService(session_scope_factory=scope, gateway=gateway))
    try:
        service.answer(AssistantMessageRequestDto(run_id="run-question-proof", message=question, request_id="evidence-omitted", idempotency_key="evidence-omitted"), actor="owner", correlation_id="evidence-omitted-correlation")
    except AssistantRequestError as error:
        assert error.code == "assistant_invalid_citation"
    else:
        raise AssertionError("citation to omitted excerpt must be rejected")
    assert reference["excerpt_id"] not in {item.segment_id for item in gateway.calls[0].context}
    engine.dispose()
