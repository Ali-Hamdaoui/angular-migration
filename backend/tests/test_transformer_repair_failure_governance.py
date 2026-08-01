"""Durable failure governance for repair LLM wiring (blocked, never livelocked)."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.contracts import ArtifactType
from app.llm_gateway import (
    AzureGatewayError,
    AzureOpenAILLMGateway,
    LlmFailureCode,
    PromptRegistry,
    PromptSchemaRegistry,
)
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    ArtifactMetadataModel,
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    UsageCostRecordModel,
)
from app.repositories.models.base import Base
from app.services.repair_application_service import (
    RepairApplicationService,
    RepairProposal,
    RepairReview,
)
from app.services.transformation_continuation_service import TransformationContinuationService
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from app.services.stage_preparation_primitives import StageSandboxCopier

NOW = datetime(2026, 7, 31, tzinfo=UTC)


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _scope(factory):
    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope


def _azure_settings(tmp_path: Path, *, retries: int = 2) -> Settings:
    return Settings(
        _env_file=None,
        artifact_root=tmp_path / "runs",
        workspace_root=tmp_path / "workspaces",
        snapshot_root=tmp_path / "snapshots",
        delivery_root=tmp_path / "delivery",
        sandbox_root=tmp_path / "sandboxes",
        llm_enabled=True,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_deployment="gpt-5-mini-private",
        azure_openai_api_version="2025-04-01-preview",
        azure_openai_api_key=SecretStr("super-secret-api-key"),
        llm_input_price_per_million_tokens=0.25,
        llm_output_price_per_million_tokens=2.0,
        llm_max_transport_retries=retries,
    )


class _FakeAzureTransport:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _responses_body(text: str) -> dict[str, object]:
    message = {
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }
    reasoning = {"type": "reasoning", "content": [], "summary": []}
    return {
        "status": "completed",
        "output": [reasoning, message],
        "usage": {"input_tokens": 11, "output_tokens": 71, "total_tokens": 82},
    }


def _proposal_payload(app_ts: Path) -> dict[str, object]:
    checksum = "sha256:" + hashlib.sha256(app_ts.read_bytes()).hexdigest()
    return {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "old_text": "old",
                "new_text": "new",
            }
        ],
        "unified_diff": None,
        "rationale": ["Fix the compiler error."],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }


def _review_payload(proposal_checksum: str) -> dict[str, object]:
    return {
        "decision": "accept",
        "findings": [],
        "policy_checks": ["paths"],
        "risk_assessment": "low risk, minimal change",
        "required_validation_targets": ["build"],
        "limitations": [],
    }


def _gateway(transport, settings, *, prompt_registry: PromptRegistry | None = None):
    schema_registry = PromptSchemaRegistry()
    from app.services.repair_application_service import RepairProposalCandidate, RepairReviewCandidate
    schema_registry.register("repair_proposer_candidate_v2", RepairProposalCandidate)
    schema_registry.register("repair_reviewer_candidate_v2", RepairReviewCandidate)
    return AzureOpenAILLMGateway(
        settings=settings,
        transport=transport,
        registry=schema_registry,
        prompt_registry=prompt_registry or PromptRegistry.defaults(),
    )


def _registry_without(*names: str) -> PromptRegistry:
    registry = PromptRegistry()
    for prompt in PromptRegistry.defaults()._prompts.values():
        if prompt.name not in names:
            registry.register(prompt)
    return registry


def _seed(
    factory,
    tmp_path: Path,
    *,
    stage_id: str = "stage-1",
    run_id: str = "run-1",
    proposed: bool = False,
):
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    app_ts = workspace / "src" / "app.ts"
    app_ts.write_text("old", encoding="utf-8")
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    attempt_id = "repair-1"
    failure = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{attempt_id}/failure-evidence.json",
        json.dumps({"attempt_id": attempt_id, "failure": "compiler", "stage_id": stage_id}),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=attempt_id,
        created_by="repair-failure-evidence",
        created_at=NOW,
    )
    context = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{attempt_id}/context-pack.json",
        json.dumps({"evidence": "bounded context"}),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=attempt_id,
        created_by="repair-context",
        created_at=NOW,
    )
    proposal = None
    if proposed:
        proposal = store.write_text_artifact(
            run_id,
            f"05_repairs/attempt-{attempt_id}/proposal.json",
            json.dumps(_proposal_payload(app_ts), sort_keys=True),
            ArtifactType.JSON,
            stage_id=stage_id,
            attempt_id=attempt_id,
            created_by="repair-proposal",
            created_at=NOW,
        )
    session = factory()
    run = MigrationRunModel(
        id=run_id,
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    plan = StageExecutionPlanModel(
        id=f"stage-plan-{stage_id}",
        run_id=run_id,
        migration_plan_id="plan-1",
        stage_id=stage_id,
        idempotency_key="plan",
        request_checksum="sha256:plan",
        actor="operator",
        correlation_id="corr-1",
        status="approved",
        version=1,
        stage_plan={"repair_policy": {"max_attempts": 3}, "forbidden_change_policy": {}},
        checksum="sha256:stage-plan",
        artifact_ids=[],
        artifact_checksums={},
        state_version=1,
        event_sequence=1,
        created_at=NOW,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id=run_id,
        stage_id=stage_id,
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=StageSandboxCopier.fingerprint(workspace),
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id=run_id,
        current_stage_id=stage_id,
        thread_id="thread-1",
        status="running",
        current_node="review_repair" if proposed else "propose_repair",
        worker_id="worker-1",
        lease_expires_at=NOW + timedelta(seconds=120),
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id=f"stage-plan-{stage_id}",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        attempt=1,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    attempt = RepairAttemptModel(
        id=attempt_id,
        run_id=run_id,
        stage_id=stage_id,
        attempt_number=1,
        status="proposed" if proposed else "evidence_frozen",
        risk_level="low" if proposed else "unknown",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id="artifact-route",
        failure_route_checksum="sha256:route",
        context_pack_artifact_id=context.ref.artifact_id,
        context_pack_checksum=context.ref.checksum,
        proposal_artifact_id=proposal.ref.artifact_id if proposed else None,
        proposal_checksum=proposal.ref.checksum if proposed else None,
        proposer_invocation_id=f"{attempt_id}:proposer" if proposed else None,
        pre_fingerprint=context.ref.checksum,
        failure_fingerprint="fingerprint-failure",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, plan, binding, continuation, attempt])
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + failure.ref.artifact_id,
            run_id=run_id,
            stage_id=stage_id,
            artifact_type=failure.ref.artifact_type.value,
            relative_path=failure.ref.relative_path,
            checksum=failure.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + context.ref.artifact_id,
            run_id=run_id,
            stage_id=stage_id,
            artifact_type=context.ref.artifact_type.value,
            relative_path=context.ref.relative_path,
            checksum=context.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    if proposed:
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + proposal.ref.artifact_id,
                run_id=run_id,
                stage_id=stage_id,
                artifact_type=proposal.ref.artifact_type.value,
                relative_path=proposal.ref.relative_path,
                checksum=proposal.ref.checksum,
                created_at=NOW,
                finalized_at=NOW,
                immutable=True,
            )
        )
        session.add(
            LlmInvocationModel(
                id=f"{attempt_id}:proposer",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key=f"{attempt_id}:proposer",
                request_checksum="sha256:request",
                input_hashes=[failure.ref.checksum, context.ref.checksum],
                correlation_id=f"{attempt_id}:proposer",
                actor="transformer",
                role="repair_proposer",
                task_type="repair_diagnosis",
                provider="azure_openai",
                deployment_alias="azure-openai",
                prompt_version="prompt-repair-proposer-v1",
                schema_version="schema-registry-v1",
                pricing_version="mvp-pricing-2026-01",
                stage="repair",
                redacted_summary=json.dumps({"risk_level": "low"}, sort_keys=True),
                status="completed",
                artifact_ids=[proposal.ref.artifact_id],
                artifact_checksums={proposal.ref.artifact_id: proposal.ref.checksum},
                state_version=1,
                event_sequence=0,
                retries=0,
                started_at=NOW,
                completed_at=NOW,
                created_at=NOW,
            )
        )
    session.commit()
    session.close()
    return store, attempt_id, app_ts, artifacts


def _orchestrator(factory, repair_service):
    scope = _scope(factory)
    return TransformerOrchestrator(
        scope=scope,
        stage_service=TransformerStageService(scope=scope),
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=repair_service,
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )


def _requeue(factory, *, node: str, worker: str) -> None:
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    continuation.status = "running"
    continuation.current_node = node
    continuation.worker_id = worker
    continuation.lease_expires_at = NOW + timedelta(seconds=120)
    continuation.state_version += 1
    session.commit()
    session.close()


def _file_inventory(artifacts: Path) -> list[str]:
    return sorted(
        str(path.relative_to(artifacts)).replace("\\", "/")
        for path in artifacts.rglob("*")
        if path.is_file()
    )


def _assert_not_reclaimable(factory) -> None:
    session = factory()
    claimed = TransformationContinuationService().claim_next(
        session, "worker-2", now=NOW + timedelta(seconds=300)
    )
    assert claimed is None
    session.close()


def test_propose_reaches_transport_with_production_registry(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, artifacts = _seed(factory, tmp_path)
    transport = _FakeAzureTransport([_responses_body(json.dumps(_proposal_payload(app_ts)))])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "review_repair"
    assert continuation.worker_id is None
    assert continuation.lease_expires_at is None
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "proposed"
    assert attempt.proposal_artifact_id is not None
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    assert invocations[0].idempotency_key == f"{attempt_id}:proposer"
    assert invocations[0].status == "completed"
    assert session.query(UsageCostRecordModel).count() == 1
    metadata = session.get(ArtifactMetadataModel, "metadata-" + attempt.proposal_artifact_id)
    assert metadata is not None
    assert metadata.relative_path == f"05_repairs/attempt-{attempt_id}/proposal.json"
    session.close()
    inventory = _file_inventory(artifacts)
    assert f"05_repairs/attempt-{attempt_id}/proposal.json" in inventory
    engine.dispose()


def test_review_reaches_transport_with_production_registry(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path, proposed=True)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    proposal_checksum = attempt.proposal_checksum
    session.close()
    transport = _FakeAzureTransport([_responses_body(json.dumps(_review_payload(proposal_checksum)))])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "create_g10"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "review_accepted"
    assert attempt.review_artifact_id is not None
    reviewers = session.query(LlmInvocationModel).filter_by(idempotency_key=f"{attempt_id}:reviewer").all()
    assert len(reviewers) == 1
    assert reviewers[0].status == "completed"
    session.close()
    inventory = _file_inventory(artifacts)
    assert f"05_repairs/attempt-{attempt_id}/review.json" in inventory
    engine.dispose()


def test_missing_prompt_policy_blocks_without_transport_or_artifact(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path)
    transport = _FakeAzureTransport([])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            transport,
            _azure_settings(tmp_path),
                prompt_registry=_registry_without("repair_proposer_candidate_v2"),
        ),
    )

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    assert transport.calls == []
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "LLM_PROMPT_POLICY_MISSING"
    assert continuation.worker_id is None
    assert continuation.lease_expires_at is None
    assert continuation.current_node == "propose_repair"
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.idempotency_key == f"{attempt_id}:proposer"
    assert invocation.status == "failed"
    assert invocation.failure_code == "LLM_PROMPT_POLICY_MISSING"
    assert invocation.failure_stage == "local"
    assert invocation.transport_started is False
    assert invocation.response_received is False
    assert invocation.provider_request_id is None
    assert invocation.retryable is False
    assert invocation.retries == 0
    assert session.query(UsageCostRecordModel).count() == 0
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "evidence_frozen"
    assert attempt.failure_evidence_checksum == session.get(ArtifactMetadataModel, "metadata-" + attempt.failure_evidence_artifact_id).checksum
    assert attempt.context_pack_checksum == session.get(ArtifactMetadataModel, "metadata-" + attempt.context_pack_artifact_id).checksum
    assert attempt.proposal_artifact_id is None
    session.close()
    _assert_not_reclaimable(factory)
    inventory = _file_inventory(artifacts)
    assert f"05_repairs/attempt-{attempt_id}/proposal.json" not in inventory
    error_path = artifacts / f"05_repairs/attempt-{attempt_id}" / "propose-error.json"
    assert error_path.is_file()
    diagnostic = json.loads(error_path.read_text(encoding="utf-8"))
    assert diagnostic["code"] == "LLM_PROMPT_POLICY_MISSING"
    assert diagnostic["retryable"] is False
    assert diagnostic["provider_request_id"] is None
    assert diagnostic["provider_status"] is None
    assert diagnostic["transport_started"] is False
    assert diagnostic["response_received"] is False
    assert diagnostic["retries"] == 0
    assert set(diagnostic) == {
        "code",
        "message",
        "retryable",
        "failure_stage",
        "provider_status",
        "provider_request_id",
        "failure_subtype",
        "provider_http_status",
        "provider_error_code",
        "sanitized_provider_message",
        "response_received",
        "transport_started",
        "response_sha256",
        "response_bytes",
        "response_kind",
        "retries",
    }
    engine.dispose()


@pytest.mark.parametrize(
    "failure, expected_code",
    [
        pytest.param(
            AzureGatewayError(
                LlmFailureCode.TIMEOUT,
                "Azure OpenAI request timed out.",
                retryable=True,
                provider_status=408,
            ),
            "LLM_PROVIDER_TIMEOUT",
            id="timeout",
        ),
        pytest.param(
            AzureGatewayError(
                LlmFailureCode.RATE_LIMIT,
                "Azure OpenAI request failed.",
                retryable=True,
                provider_status=429,
            ),
            "LLM_PROVIDER_RATE_LIMIT",
            id="rate-limit",
        ),
        pytest.param(
            AzureGatewayError(
                LlmFailureCode.SERVER,
                "Azure OpenAI request failed.",
                retryable=True,
                provider_status=503,
            ),
            "LLM_PROVIDER_UNAVAILABLE",
            id="server-503",
        ),
    ],
)
def test_provider_timeout_429_5xx_bounded_then_blocked(
    tmp_path: Path, monkeypatch, failure, expected_code
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path)
    monkeypatch.setattr("app.llm_gateway.azure_gateway.time.sleep", lambda _seconds: None)
    retries = 2
    transport = _FakeAzureTransport([failure] * (1 + retries))
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path, retries=retries)),
    )

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1 + retries
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == expected_code
    assert continuation.worker_id is None
    assert continuation.lease_expires_at is None
    assert continuation.current_node == "propose_repair"
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.status == "failed"
    assert invocation.failure_code == expected_code
    assert invocation.transport_started is False
    assert invocation.response_received is False
    assert invocation.provider_request_id is None
    assert invocation.retries == retries
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "evidence_frozen"
    assert attempt.proposal_artifact_id is None
    session.close()
    _assert_not_reclaimable(factory)
    inventory = _file_inventory(artifacts)
    assert f"05_repairs/attempt-{attempt_id}/proposal.json" not in inventory
    assert any(name.endswith("/propose-error.json") for name in inventory)
    engine.dispose()


@pytest.mark.parametrize(
    "failure, expected_code",
    [
        pytest.param(
            AzureGatewayError(
                LlmFailureCode.INVALID_REQUEST,
                "Azure OpenAI request failed.",
                retryable=False,
                provider_status=400,
            ),
            "LLM_PROVIDER_BAD_REQUEST",
            id="bad-request",
        ),
        pytest.param(
            AzureGatewayError(
                LlmFailureCode.AUTHENTICATION,
                "Azure OpenAI request failed.",
                retryable=False,
                provider_status=401,
            ),
            "LLM_PROVIDER_AUTH",
            id="auth",
        ),
    ],
)
def test_provider_400_and_auth_block_without_repeated_claims(tmp_path: Path, failure, expected_code):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path)
    transport = _FakeAzureTransport([failure])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == expected_code
    assert continuation.worker_id is None
    assert continuation.lease_expires_at is None
    assert continuation.current_node == "propose_repair"
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.status == "failed"
    assert invocation.failure_code == expected_code
    assert invocation.transport_started is False
    assert invocation.response_received is False
    assert invocation.provider_request_id is None
    assert invocation.retries == 0
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "evidence_frozen"
    session.close()
    _assert_not_reclaimable(factory)
    inventory = _file_inventory(artifacts)
    assert f"05_repairs/attempt-{attempt_id}/proposal.json" not in inventory
    engine.dispose()


def test_successful_proposer_replay_no_duplicate_calls_or_artifacts(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, artifacts = _seed(factory, tmp_path)
    transport = _FakeAzureTransport([_responses_body(json.dumps(_proposal_payload(app_ts)))])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )
    orchestrator = _orchestrator(factory, repair_service)

    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1
    assert session.query(LlmInvocationModel).count() == 1
    session.close()
    inventory_before = _file_inventory(artifacts)

    _requeue(factory, node="propose_repair", worker="worker-2")
    orchestrator.advance("cont-1", "worker-2")

    session = factory()
    assert len(transport.calls) == 1
    assert session.query(LlmInvocationModel).count() == 1
    assert session.query(UsageCostRecordModel).count() == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "review_repair"
    assert continuation.worker_id is None
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "proposed"
    session.close()
    inventory = _file_inventory(artifacts)
    assert inventory == inventory_before
    assert (
        sum(name.endswith("/proposal.json") for name in inventory) == 1
    )
    engine.dispose()


def test_successful_review_replay(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path, proposed=True)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    proposal_checksum = attempt.proposal_checksum
    session.close()
    transport = _FakeAzureTransport([_responses_body(json.dumps(_review_payload(proposal_checksum)))])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )
    orchestrator = _orchestrator(factory, repair_service)

    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1
    assert session.query(LlmInvocationModel).count() == 2
    session.close()
    inventory_before = _file_inventory(artifacts)

    _requeue(factory, node="review_repair", worker="worker-2")
    orchestrator.advance("cont-1", "worker-2")

    session = factory()
    assert len(transport.calls) == 1
    assert session.query(LlmInvocationModel).count() == 2
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "create_g10"
    assert continuation.worker_id is None
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "review_accepted"
    session.close()
    inventory = _file_inventory(artifacts)
    assert inventory == inventory_before
    assert sum(name.endswith("/review.json") for name in inventory) == 1
    engine.dispose()


def test_llm_configuration_invalid_blocks_durably(tmp_path: Path, monkeypatch):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path)
    bad_settings = _azure_settings(tmp_path).model_copy(update={"azure_openai_api_key": None})
    monkeypatch.setattr(
        "app.services.repair_application_service.get_settings", lambda: bad_settings
    )
    repair_service = RepairApplicationService(scope=_scope(factory), gateway=None)

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "LLM_CONFIGURATION_INVALID"
    assert continuation.worker_id is None
    assert continuation.lease_expires_at is None
    assert continuation.current_node == "propose_repair"
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.status == "failed"
    assert invocation.failure_code == "LLM_CONFIGURATION_INVALID"
    assert invocation.failure_stage == "local"
    assert invocation.transport_started is False
    assert invocation.provider_request_id is None
    assert invocation.retryable is False
    assert session.query(UsageCostRecordModel).count() == 0
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "evidence_frozen"
    assert attempt.proposal_artifact_id is None
    session.close()
    _assert_not_reclaimable(factory)
    error_path = artifacts / f"05_repairs/attempt-{attempt_id}" / "propose-error.json"
    assert error_path.is_file()
    diagnostic = json.loads(error_path.read_text(encoding="utf-8"))
    assert diagnostic["code"] == "LLM_CONFIGURATION_INVALID"
    assert diagnostic["retryable"] is False
    assert diagnostic["provider_request_id"] is None
    assert f"05_repairs/attempt-{attempt_id}/proposal.json" not in _file_inventory(artifacts)
    engine.dispose()


def test_evidence_missing_blocks_durably(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path)
    context_pack = artifacts / "05_repairs" / f"attempt-{attempt_id}" / "context-pack.json"
    assert context_pack.is_file()
    context_pack.unlink()
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(_FakeAzureTransport([]), _azure_settings(tmp_path)),
    )

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_EVIDENCE_MISSING"
    assert continuation.worker_id is None
    assert continuation.lease_expires_at is None
    assert continuation.current_node == "propose_repair"
    # REPAIR_EVIDENCE_MISSING fails inside _attempt_context, before any invocation is created.
    assert session.query(LlmInvocationModel).count() == 0
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "evidence_frozen"
    session.close()
    _assert_not_reclaimable(factory)
    engine.dispose()


def test_schema_validation_failure_persists_failed_invocation_row(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path)
    out_of_vocabulary = {
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "proposal_format": "operations",
        "operations": [{"operation": "modify_file", "path": "src/app.ts"}],
        "touched_files": ["src/app.ts"],
        "rationale": ["x"],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }
    transport = _FakeAzureTransport([_responses_body(json.dumps(out_of_vocabulary))])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert continuation.current_node == "propose_repair"
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.status == "failed"
    assert invocation.failure_code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert invocation.failure_stage == "schema_validation"
    assert invocation.failure_subtype == "ASSISTANT_SCHEMA_VALIDATION"
    assert invocation.role == "repair_proposer"
    assert invocation.transport_started is True
    assert invocation.response_received is True
    assert invocation.provider_request_id is None
    assert session.query(UsageCostRecordModel).count() == 0
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "evidence_frozen"
    assert attempt.proposal_artifact_id is None
    session.close()
    _assert_not_reclaimable(factory)
    inventory = _file_inventory(artifacts)
    assert f"05_repairs/attempt-{attempt_id}/proposal.json" not in inventory
    assert any(name.endswith("/propose-error.json") for name in inventory)
    engine.dispose()


def test_failed_invocation_replay_updates_same_row_after_requeue(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, _artifacts = _seed(factory, tmp_path)
    failure = AzureGatewayError(
        LlmFailureCode.INVALID_REQUEST,
        "Azure OpenAI request failed.",
        retryable=False,
        provider_status=400,
    )
    transport = _FakeAzureTransport([failure, _responses_body(json.dumps(_proposal_payload(app_ts)))])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )
    orchestrator = _orchestrator(factory, repair_service)

    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "LLM_PROVIDER_BAD_REQUEST"
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    assert invocations[0].status == "failed"
    session.close()

    _requeue(factory, node="propose_repair", worker="worker-2")
    orchestrator.advance("cont-1", "worker-2")

    session = factory()
    assert len(transport.calls) == 2
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    assert invocations[0].id == f"{attempt_id}:proposer"
    assert invocations[0].status == "completed"
    assert invocations[0].failure_code is None
    assert session.query(UsageCostRecordModel).count() == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "review_repair"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "proposed"
    session.close()
    engine.dispose()


def test_failed_reviewer_persists_failed_invocation_row(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed(factory, tmp_path, proposed=True)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    proposal_checksum = attempt.proposal_checksum
    session.close()
    assert proposal_checksum != "sha256:different"
    stale_review = _review_payload("sha256:different")
    stale_review["proposal_checksum"] = "sha256:different"
    transport = _FakeAzureTransport([_responses_body(json.dumps(stale_review))])
    repair_service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )

    _orchestrator(factory, repair_service).advance("cont-1", "worker-1")

    session = factory()
    assert len(transport.calls) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert continuation.current_node == "review_repair"
    reviewers = (
        session.query(LlmInvocationModel)
        .filter_by(idempotency_key=f"{attempt_id}:reviewer")
        .all()
    )
    assert len(reviewers) == 1
    assert reviewers[0].status == "failed"
    assert reviewers[0].failure_code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert reviewers[0].failure_stage == "schema_validation"
    assert reviewers[0].transport_started is True
    assert reviewers[0].response_received is True
    assert reviewers[0].provider_request_id is None
    assert session.query(UsageCostRecordModel).count() == 0
    session.close()
    _assert_not_reclaimable(factory)
    inventory = _file_inventory(artifacts)
    assert f"05_repairs/attempt-{attempt_id}/review.json" not in inventory
    assert any(name.endswith("/review-error.json") for name in inventory)
    engine.dispose()


def test_apply_preflight_failure_does_not_reconstruct_workspace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sentinel = workspace / "sentinel.txt"
    sentinel.write_text("untouched\n", encoding="utf-8")
    continuation = SimpleNamespace(run_id="run-1", current_stage_id="stage-1")
    binding = SimpleNamespace(workspace_path=str(workspace))
    scope_calls = []

    @contextmanager
    def scope():
        scope_calls.append(True)
        yield SimpleNamespace()

    orchestrator = TransformerOrchestrator.__new__(TransformerOrchestrator)
    orchestrator._scope = scope
    orchestrator._owned = lambda _session, _continuation_id, _worker_id: continuation
    orchestrator._stage = SimpleNamespace(_binding=lambda _session, _continuation: binding)
    orchestrator._apply_repair_locked = MagicMock(
        side_effect=TransformerStageError("G10_APPROVAL_REQUIRED", "approval missing")
    )

    with pytest.raises(ValueError, match="approval missing"):
        orchestrator._apply_repair("cont-1", "worker-1")

    assert scope_calls
    assert sentinel.read_text(encoding="utf-8") == "untouched\n"


def test_apply_recovery_state_write_failure_is_not_silenced():
    @contextmanager
    def failing_scope():
        raise RuntimeError("database unavailable")
        yield

    orchestrator = TransformerOrchestrator.__new__(TransformerOrchestrator)
    orchestrator._scope = failing_scope

    with pytest.raises(RuntimeError, match="database unavailable"):
        orchestrator._mark_apply_recovery_required("cont-1", None)
