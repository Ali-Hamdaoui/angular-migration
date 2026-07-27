import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.llm_contracts import LlmSmokeRequest
from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.contracts import AgentKind, WorkflowEventType
from app.llm_gateway import AzureGatewayError, AzureOpenAILLMGateway, LlmFailureCode, LlmRequest, LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, PromptSchemaRegistry, build_usage_record
from app.llm_gateway.contracts import LlmContextSegment
from app.repositories.models import ArtifactMetadataModel, Base, LlmInvocationModel, MigrationRunModel, UsageCostRecordModel, WorkflowEventModel
from app.services.llm_evidence_application_service import AssistantInvocationRequest, LlmEvidenceApplicationService, _AssistantResponse

NOW = datetime(2026, 7, 18, tzinfo=UTC)


class FakeGateway:
    def __init__(self, *, fail: Exception | None = None):
        self.fail = fail
        self.deployment_name = 'resolved-deployment'

    def complete(self, request: LlmRequest):
        if self.fail:
            raise self.fail
        usage = build_usage_record(run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ANALYSIS, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias='azure-openai', input_tokens=10, output_tokens=5, input_price_per_million=0.25, output_price_per_million=2.0)
        return LlmResponse(response_id='response-1', request_id=request.request_id, run_id=request.run_id, agent_kind=request.agent_kind, task_type=request.task_type, model_deployment_alias='azure-openai', status='completed', summary='ok', structured_output={'answer': 'ok'}, usage=usage, redaction=PromptRedactionResult(redacted_text='safe', redaction_count=0), role=LlmRole.PHASE_PROPOSER, prompt_version='migration-policy-v1', schema_version='schema-registry-v1', pricing_version='mvp-pricing-2026-01')


def fixture(tmp_path: Path):
    db_path = tmp_path / 'state.db'
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id='run-1', status='CREATED', run_phase='DISCOVERY_BASELINE', phase_status='running', approval_status='approved', repair_status='not_required', state_version=1, artifact_root=str(tmp_path / 'artifacts'), created_at=NOW, updated_at=NOW))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    settings = Settings(_env_file=None, artifact_root=tmp_path / 'artifacts', workspace_root=tmp_path / 'workspaces', snapshot_root=tmp_path / 'snapshots', delivery_root=tmp_path / 'delivery', sandbox_root=tmp_path / 'sandboxes', llm_enabled=False, azure_openai_api_key=SecretStr('not-used'))
    return scope, sessions, settings, engine


def request(key='smoke-1', version=1):
    return LlmSmokeRequest(run_id='run-1', expected_state_version=version, idempotency_key=key, correlation_id='corr-1')


def test_smoke_persists_immutable_artifacts_usage_and_ordered_events(tmp_path):
    scope, sessions, settings, engine = fixture(tmp_path)
    service = LlmEvidenceApplicationService(settings=settings, session_scope_factory=scope, gateway=FakeGateway(), now_provider=lambda: NOW)

    result = service.smoke(request())
    replay = service.smoke(request())

    assert result.status == 'completed'
    assert replay.idempotent_replay is True
    assert result.total_tokens == 15
    assert result.total_cost_usd == pytest.approx(0.0000125)
    assert len(result.artifact_ids) == 3
    with sessions() as session:
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == 'run-1').order_by(WorkflowEventModel.sequence)))
        assert [event.event_type for event in events] == [WorkflowEventType.LLM_INVOCATION_STARTED.value, WorkflowEventType.LLM_INVOCATION_COMPLETED.value]
        assert session.scalar(select(LlmInvocationModel)) is not None
        assert session.scalar(select(LlmInvocationModel)).deployment_alias == 'resolved-deployment'
        assert session.scalar(select(UsageCostRecordModel)) is not None
        assert session.scalar(select(ArtifactMetadataModel)) is not None
    engine.dispose()


def test_smoke_rejects_stale_and_idempotency_conflict_before_duplicate_side_effects(tmp_path):
    scope, sessions, settings, engine = fixture(tmp_path)
    service = LlmEvidenceApplicationService(settings=settings, session_scope_factory=scope, gateway=FakeGateway(), now_provider=lambda: NOW)
    with pytest.raises(Exception) as stale:
        service.smoke(request('stale', version=2))
    assert stale.value.code == 'STALE_STATE_VERSION'
    service.smoke(request())
    with pytest.raises(Exception) as conflict:
        service.smoke(LlmSmokeRequest(run_id='run-1', expected_state_version=1, idempotency_key='smoke-1', correlation_id='different'))
    assert conflict.value.code == 'IDEMPOTENCY_KEY_REUSED'
    engine.dispose()


def test_smoke_failure_persists_redacted_failure_evidence(tmp_path):
    scope, sessions, settings, engine = fixture(tmp_path)
    service = LlmEvidenceApplicationService(settings=settings, session_scope_factory=scope, gateway=FakeGateway(fail=RuntimeError('provider secret')), now_provider=lambda: NOW)

    result = service.smoke(request('failure'))

    assert result.status == 'failed'
    assert result.failure_code == 'LLM_PROVIDER_FAILURE'
    assert len(result.artifact_ids) == 1
    with sessions() as session:
        event = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.event_type == WorkflowEventType.LLM_INVOCATION_FAILED.value))
        assert event is not None
    engine.dispose()


def test_smoke_persists_specific_provider_failure_metadata(tmp_path):
    scope, sessions, settings, engine = fixture(tmp_path)
    failure = AzureGatewayError(LlmFailureCode.SERVER, 'provider failed', provider_status=500, provider_code='InternalServerError', provider_message='safe provider message', provider_request_id='azure-request-1')
    service = LlmEvidenceApplicationService(settings=settings, session_scope_factory=scope, gateway=FakeGateway(fail=failure), now_provider=lambda: NOW)

    result = service.smoke(request('provider-failure'))

    with sessions() as session:
        artifact = LocalFilesystemArtifactStore(tmp_path / 'artifacts', fixed_run_root=tmp_path / 'artifacts').read_artifact_by_id(result.artifact_ids[0])
        payload = json.loads(artifact.content)
        assert payload == {'error_code': 'server', 'message': 'LLM invocation failed.', 'provider_error_code': 'InternalServerError', 'provider_http_status': 500, 'provider_message': 'safe provider message', 'provider_request_id': 'azure-request-1', 'resolved_deployment': 'resolved-deployment'}


def test_assistant_service_reaches_real_gateway_with_typed_policy_and_mocked_azure(tmp_path):
    scope, sessions, settings, engine = fixture(tmp_path)
    settings = settings.model_copy(update={
        'llm_enabled': True,
        'azure_openai_endpoint': 'https://example.openai.azure.com',
        'azure_openai_deployment': 'gpt-5-mini',
        'azure_openai_api_version': '2025-04-01-preview',
    })

    class Transport:
        def __init__(self):
            self.calls = []

        def request(self, **kwargs):
            self.calls.append(kwargs)
            return {'status': 'completed', 'output': [{'type': 'reasoning', 'content': [], 'summary': []}, {'type': 'message', 'status': 'completed', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps({'answer': 'ok', 'citations': []})}]}], 'usage': {'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5}}

    transport = Transport()
    registry = PromptSchemaRegistry()
    registry.register('assistant-response-v1', _AssistantResponse)
    gateway = AzureOpenAILLMGateway(settings=settings, transport=transport, registry=registry)
    service = LlmEvidenceApplicationService(settings=settings, session_scope_factory=scope, gateway=gateway, now_provider=lambda: NOW)

    result = service.assistant(AssistantInvocationRequest(run_id='run-1', expected_state_version=1, idempotency_key='assistant-1', correlation_id='corr-1', question='SENTINEL_QUESTION', context=[LlmContextSegment(segment_id='history', label='SENTINEL_LABEL', content='SENTINEL_CONTEXT')]))

    assert result.status == 'completed'
    assert transport.calls[0]['deployment'] == 'gpt-5-mini'
    assert transport.calls[0]['payload']['model'] == 'gpt-5-mini'
    assert transport.calls[0]['payload']['max_output_tokens'] == 20_000
    assert transport.calls[0]['payload']['text']['format']['strict'] is True
    assert transport.calls[0]['payload']['text']['format']['name'] == 'assistant-response-v1'
    assert transport.calls[0]['payload']['text']['format']['type'] == 'json_schema'
    assert set(transport.calls[0]['payload']['text']['format']['schema']['required']) == {'answer', 'citations'}
    schema = transport.calls[0]['payload']['text']['format']['schema']
    citation_schema = transport.calls[0]['payload']['text']['format']['schema']['$defs']['_AssistantCitation']
    assert schema['additionalProperties'] is False
    assert citation_schema['additionalProperties'] is False
    assert set(citation_schema['required']) == {'artifact_id', 'checksum', 'stage_id'}
    assert 'response_format' not in transport.calls[0]['payload']
    assert 'temperature' not in transport.calls[0]['payload']
    assert result.role == 'assistant'
    assert result.task_type == 'assistant_response'
    assert result.prompt_version == 'assistant-response-v1'
    assert result.latency_ms is not None
    assert result.structured_output == {'answer': 'ok', 'citations': []}
    assert result.artifact_ids
    assert 'SENTINEL_QUESTION' not in (result.redacted_summary or '')
    assert 'SENTINEL_CONTEXT' not in (result.redacted_summary or '')
    assert 'SENTINEL_LABEL' in (result.redacted_summary or '')
    activity = service.activity('run-1')
    assert activity.invocations[0].structured_output == {'answer': 'ok', 'citations': []}
    assert 'SENTINEL_CONTEXT' not in (activity.invocations[0].redacted_summary or '')
    with sessions() as session:
        invocation = session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.id == result.invocation_id))
        assert invocation is not None and invocation.status == 'completed' and invocation.failure_code is None and invocation.latency_ms is not None
        assert session.scalar(select(UsageCostRecordModel).where(UsageCostRecordModel.invocation_id == result.invocation_id)) is not None
    engine.dispose()
