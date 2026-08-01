"""Regression tests for pre-attempt repair evidence envelopes.

Production defect (run-6f89ac89792a): ``RepairApplicationService._attempt_context``
rejects failure-evidence and context-pack artifacts whose envelope carries
``attempt_id=NULL``, even though those artifacts are written by
``FailureEvidenceService`` BEFORE the ``RepairAttempt`` row exists (the attempt
is created later in ``_classify_failure``). The old fixtures masked this by
injecting the later-created attempt id into pre-attempt sidecars.

These tests seed pre-attempt evidence through the REAL ``FailureEvidenceService``
writers, so the envelope sidecars legitimately carry ``attempt_id=NULL``, and
exercise the real ``LocalFilesystemArtifactStore`` envelope validator. Only the
LLM/transport call is faked. Contract that must survive the fix (never weakened):

1. Pre-attempt failure/context envelopes may carry ``attempt_id=NULL``.
2. Their checksums, run_id and stage_id must still match.
3. A non-NULL wrong attempt_id must still be rejected.
4. Proposal/review artifacts stay attempt-bound (exact RepairAttempt ID).
5. Completed proposal replay keeps strict artifact and lineage validation.
6. Failed-invocation replay reuses the same logical invocation row and reaches
   the provider lifecycle branch.
7. in_progress + transport_started stays fail-closed REPAIR_INVOCATION_UNCERTAIN.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.contracts import ArtifactType
from app.domain.transformation import FailureRoute
from app.llm_gateway import (
    AzureOpenAILLMGateway,
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
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
    RepairProposalCandidate,
    RepairReviewCandidate,
)
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformation_continuation_service import TransformationContinuationService
from app.services.transformer_stage_service import TransformerStageService

NOW = datetime(2026, 7, 31, tzinfo=UTC)
FINGERPRINT = "sha256:" + "f" * 64


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


def _azure_settings(tmp_path: Path) -> Settings:
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


def _proposal_candidate(app_ts: Path) -> dict[str, object]:
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


def _full_proposal(app_ts: Path, failure_checksum: str, context_checksum: str) -> dict[str, object]:
    return {
        "failure_evidence_checksum": failure_checksum,
        "context_pack_checksum": context_checksum,
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "preimage_sha256": "sha256:" + hashlib.sha256(app_ts.read_bytes()).hexdigest(),
                "old_text": "old",
                "new_text": "new",
            }
        ],
        "unified_diff": None,
        "touched_files": ["src/app.ts"],
        "rationale": ["Fix the compiler error."],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }


def _gateway(transport, settings: Settings):
    schema_registry = PromptSchemaRegistry()
    schema_registry.register("repair_proposer_candidate_v2", RepairProposalCandidate)
    schema_registry.register("repair_reviewer_candidate_v2", RepairReviewCandidate)
    return AzureOpenAILLMGateway(
        settings=settings,
        transport=transport,
        registry=schema_registry,
        prompt_registry=PromptRegistry.defaults(),
    )


def _seed_pre_attempt(
    factory,
    tmp_path: Path,
    *,
    run_id: str = "run-1",
    stage_id: str = "stage-1",
    attempt_id: str = "repair-1",
    blocked: bool = False,
):
    """Seed a production-shaped run: evidence artifacts written BEFORE the attempt.

    The failure-evidence and context-pack artifacts go through the REAL
    ``FailureEvidenceService`` writers, which never bind an attempt id, so the
    sidecar envelopes carry ``attempt_id=NULL`` exactly like production.
    """
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    app_ts = workspace / "src" / "app.ts"
    app_ts.write_text("old", encoding="utf-8")
    (workspace / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    evidence = {
        "schema_version": "transformer-failure-evidence-v1",
        "run_id": run_id,
        "stage_id": stage_id,
        "stage_plan_checksum": "sha256:stage-plan",
        "workspace_path": str(workspace),
        "workspace_fingerprint": StageSandboxCopier.fingerprint(workspace),
        "artifact_root": str(artifacts),
        "execution_id": "execution-1",
        "command_log_artifact_id": None,
        "result_artifact_id": None,
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
    evidence_service = FailureEvidenceService()
    failure, route_artifact = evidence_service.write(evidence, FailureRoute.REPAIRABLE_SOURCE)
    context = evidence_service.write_context_pack(evidence, failure.ref.checksum)
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
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
        status="blocked" if blocked else "running",
        current_node="propose_repair",
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id=plan.id,
        stage_plan_checksum=plan.checksum,
        worker_id=None if blocked else "worker-1",
        attempt=1,
        max_attempts=3,
        lease_expires_at=None if blocked else NOW + timedelta(seconds=120),
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        last_error_code="REPAIR_ARTIFACT_RECOVERY_FAILED" if blocked else None,
        last_error_message="Repair artifact envelope binding is stale" if blocked else None,
        created_at=NOW,
        updated_at=NOW,
    )
    # The RepairAttempt row is created AFTER the pre-attempt evidence artifacts,
    # exactly like _classify_failure does in production.
    attempt = RepairAttemptModel(
        id=attempt_id,
        run_id=run_id,
        stage_id=stage_id,
        attempt_number=1,
        status="evidence_frozen",
        risk_level="unknown",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id=route_artifact.ref.artifact_id,
        failure_route_checksum=route_artifact.ref.checksum,
        context_pack_artifact_id=context.ref.artifact_id,
        context_pack_checksum=context.ref.checksum,
        proposal_artifact_id=None,
        proposal_checksum=None,
        proposer_invocation_id=None,
        failure_fingerprint=FINGERPRINT,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, plan, binding, continuation, attempt])
    for stored in (failure, context):
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + stored.ref.artifact_id,
                run_id=run_id,
                stage_id=stage_id,
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=NOW,
                finalized_at=NOW,
                immutable=True,
            )
        )
    session.commit()
    session.close()
    return store, attempt_id, app_ts, artifacts, failure, route_artifact, context


def _seed_failed_proposer(
    factory, attempt_id: str, *, run_id: str = "run-1", stage_id: str = "stage-1"
) -> None:
    session = factory()
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id=run_id,
            stage_id=stage_id,
            idempotency_key=f"{attempt_id}:proposer",
            request_checksum="sha256:legacy-request",
            input_hashes=["sha256:legacy-failure", "schema:legacy-v1"],
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
            redacted_summary=None,
            status="failed",
            failure_code="LLM_PROVIDER_BAD_REQUEST",
            artifact_ids=[],
            artifact_checksums={},
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


def _seed_completed_proposal(
    factory, store, attempt_id: str, app_ts: Path, artifacts: Path
) -> tuple[dict[str, object], str, str]:
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    payload = _full_proposal(
        app_ts, attempt.failure_evidence_checksum, attempt.context_pack_checksum
    )
    session.close()
    proposal = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(payload, sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-proposal",
        created_at=NOW,
    )
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.proposal_artifact_id = proposal.ref.artifact_id
    attempt.proposal_checksum = proposal.ref.checksum
    attempt.proposer_invocation_id = f"{attempt_id}:proposer"
    attempt.status = "proposed"
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key=f"{attempt_id}:proposer",
            request_checksum="sha256:v1-request",
            input_hashes=[attempt.failure_evidence_checksum, attempt.context_pack_checksum],
            correlation_id=f"{attempt_id}:proposer",
            actor="transformer",
            role="repair_proposer",
            task_type="repair_diagnosis",
            provider="azure_openai",
            deployment_alias="azure-openai",
            prompt_version="repair-proposer-v1",
            schema_version="schema-registry-v1",
            pricing_version="mvp-pricing-2026-01",
            stage="repair",
            redacted_summary=None,
            status="completed",
            artifact_ids=[proposal.ref.artifact_id],
            artifact_checksums={proposal.ref.artifact_id: proposal.ref.checksum},
            state_version=1,
            event_sequence=0,
            retries=0,
            transport_started=True,
            started_at=NOW,
            completed_at=NOW,
            created_at=NOW,
        )
    )
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + proposal.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=proposal.ref.artifact_type.value,
            relative_path=proposal.ref.relative_path,
            checksum=proposal.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.commit()
    session.close()
    return payload, proposal.ref.relative_path, proposal.ref.artifact_id


def _read_envelope(artifacts: Path, relative_path: str) -> dict[str, object]:
    return json.loads((artifacts / f"{relative_path}.meta.json").read_text(encoding="utf-8"))


def _rewrite_sidecar(artifacts: Path, relative_path: str, **updates) -> None:
    sidecar = artifacts / f"{relative_path}.meta.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload.update(updates)
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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


def test_failed_proposer_replay_with_real_pre_attempt_evidence(tmp_path: Path):
    """Failed proposer invocation replays through the provider lifecycle.

    RED until the fix: ``_attempt_context`` raises
    REPAIR_ARTIFACT_RECOVERY_FAILED "Repair artifact envelope binding is stale"
    because the pre-attempt envelopes carry attempt_id=NULL. Every other input
    (artifacts, checksums, run/stage binding) is proven valid below, so the
    failure can only be caused by the NULL attempt_id binding.
    """
    engine, factory = _database(tmp_path)
    store, attempt_id, app_ts, artifacts, failure, _route, context = _seed_pre_attempt(
        factory, tmp_path
    )
    _seed_failed_proposer(factory, attempt_id)

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    failure_row = session.get(ArtifactMetadataModel, "metadata-" + failure.ref.artifact_id)
    context_row = session.get(ArtifactMetadataModel, "metadata-" + context.ref.artifact_id)
    assert failure_row is not None and context_row is not None
    assert failure_row.checksum == attempt.failure_evidence_checksum
    assert context_row.checksum == attempt.context_pack_checksum
    session.close()
    assert (
        store.read_artifact("run-1", failure.ref.relative_path).ref.checksum
        == failure.ref.checksum
    )
    assert (
        store.read_artifact("run-1", context.ref.relative_path).ref.checksum
        == context.ref.checksum
    )
    for stored in (failure, context):
        envelope = _read_envelope(artifacts, stored.ref.relative_path)
        assert envelope["attempt_id"] is None
        assert envelope["run_id"] == "run-1"
        assert envelope["stage_id"] == "stage-1"
        assert envelope["content_hash"] == stored.ref.checksum

    transport = _FakeAzureTransport([_responses_body(json.dumps(_proposal_candidate(app_ts)))])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    proposal = service.propose(attempt_id)

    assert len(transport.calls) == 1
    assert proposal["risk_level"] == "low"
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    assert invocations[0].idempotency_key == f"{attempt_id}:proposer"
    assert invocations[0].status == "completed"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "proposed"
    assert attempt.proposal_artifact_id is not None
    assert session.query(UsageCostRecordModel).count() == 1
    session.close()
    engine.dispose()


def test_wrong_non_null_pre_attempt_attempt_id_rejected(tmp_path: Path):
    """A non-NULL wrong attempt_id on pre-attempt evidence stays rejected."""
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts, failure, _route, context = _seed_pre_attempt(
        factory, tmp_path
    )
    for stored in (failure, context):
        _rewrite_sidecar(artifacts, stored.ref.relative_path, attempt_id="repair-other")
        envelope = _read_envelope(artifacts, stored.ref.relative_path)
        assert envelope["attempt_id"] == "repair-other"
    transport = _FakeAzureTransport([])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_ARTIFACT_RECOVERY_FAILED"
    assert raised.value.message == "Repair artifact envelope binding is stale"
    assert transport.calls == []
    session = factory()
    assert session.query(LlmInvocationModel).count() == 0
    session.close()
    engine.dispose()


def test_completed_proposal_replay_strict(tmp_path: Path):
    """Completed proposal replay keeps strict artifact and lineage validation.

    A correct attempt-bound proposal envelope replays without any provider call;
    a wrong proposal attempt_id, run_id, stage_id, or checksum still blocks with
    REPAIR_ARTIFACT_RECOVERY_FAILED even though the pre-attempt evidence is valid.
    """
    engine, factory = _database(tmp_path)
    store, attempt_id, app_ts, artifacts, _failure, _route, _context = _seed_pre_attempt(
        factory, tmp_path
    )
    payload, proposal_path, proposal_artifact_id = _seed_completed_proposal(
        factory, store, attempt_id, app_ts, artifacts
    )
    transport = _FakeAzureTransport([])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    replayed = service.propose(attempt_id)
    assert replayed == payload
    assert transport.calls == []

    for label, update in (
        ("attempt_id", {"attempt_id": "repair-other"}),
        ("run_id", {"run_id": "run-other"}),
        ("stage_id", {"stage_id": "stage-other"}),
    ):
        _rewrite_sidecar(artifacts, proposal_path, **update)
        with pytest.raises(RepairApplicationError) as raised:
            service.review(attempt_id)
        assert raised.value.code == "REPAIR_ARTIFACT_RECOVERY_FAILED"
        assert raised.value.message == "Repair artifact envelope binding is stale"
        assert transport.calls == []
        _rewrite_sidecar(
            artifacts, proposal_path, attempt_id=attempt_id, run_id="run-1", stage_id="stage-1"
        )

    session = factory()
    metadata = session.get(ArtifactMetadataModel, "metadata-" + proposal_artifact_id)
    assert metadata is not None
    metadata.checksum = "sha256:stale-row-value"
    session.commit()
    session.close()
    with pytest.raises(RepairApplicationError) as raised:
        service.review(attempt_id)
    assert raised.value.code == "REPAIR_ARTIFACT_RECOVERY_FAILED"
    assert transport.calls == []
    engine.dispose()


def test_failed_invocation_cannot_replay_stray_proposal_artifact(tmp_path: Path):
    """A failed invocation with no proposal binding never adopts a stray artifact."""
    engine, factory = _database(tmp_path)
    store, attempt_id, app_ts, artifacts, _failure, _route, _context = _seed_pre_attempt(
        factory, tmp_path
    )
    _seed_failed_proposer(factory, attempt_id)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    failure_checksum = attempt.failure_evidence_checksum
    context_checksum = attempt.context_pack_checksum
    session.close()
    stray = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(_full_proposal(app_ts, failure_checksum, context_checksum), sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id="repair-other",
        created_by="repair-proposal",
        created_at=NOW,
    )
    session = factory()
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + stray.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=stray.ref.artifact_type.value,
            relative_path=stray.ref.relative_path,
            checksum=stray.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.commit()
    session.close()
    transport = _FakeAzureTransport([_responses_body(json.dumps(_proposal_candidate(app_ts)))])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    service.propose(attempt_id)

    assert len(transport.calls) == 1
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    assert invocations[0].id == f"{attempt_id}:proposer"
    assert invocations[0].status == "completed"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "proposed"
    assert attempt.proposal_artifact_id != stray.ref.artifact_id
    assert attempt.proposal_checksum != stray.ref.checksum
    bound = session.get(ArtifactMetadataModel, "metadata-" + attempt.proposal_artifact_id)
    assert bound is not None
    assert bound.relative_path != stray.ref.relative_path
    session.close()
    engine.dispose()


def test_uncertain_invocation_fail_closed(tmp_path: Path):
    """in_progress + transport_started stays REPAIR_INVOCATION_UNCERTAIN."""
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts, _failure, _route, _context = _seed_pre_attempt(
        factory, tmp_path
    )
    session = factory()
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key=f"{attempt_id}:proposer",
            request_checksum="sha256:request",
            input_hashes=[],
            correlation_id=f"{attempt_id}:proposer",
            actor="transformer",
            role="repair_proposer",
            task_type="repair_diagnosis",
            provider="azure_openai",
            deployment_alias="azure-openai",
            prompt_version="repair-proposer-v1",
            schema_version="schema-registry-v1",
            pricing_version="mvp-pricing-2026-01",
            stage="repair",
            redacted_summary=None,
            status="in_progress",
            failure_code=None,
            artifact_ids=[],
            artifact_checksums={},
            state_version=2,
            event_sequence=0,
            retries=0,
            transport_started=True,
            started_at=NOW,
            created_at=NOW,
        )
    )
    session.commit()
    session.close()
    transport = _FakeAzureTransport([])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_INVOCATION_UNCERTAIN"
    assert transport.calls == []
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    assert invocations[0].status == "in_progress"
    assert invocations[0].transport_started is True
    session.close()
    engine.dispose()


def test_graph_shaped_recovery_reaches_failed_replay(tmp_path: Path):
    """Blocked continuation -> wake -> claim -> propose_repair reaches provider.

    Reproduces the run-6f89ac89792a lifecycle: the continuation is durably
    blocked at propose_repair with REPAIR_ARTIFACT_RECOVERY_FAILED; a
    restart-equivalent wake re-queues it; a worker claims it; advancing the
    graph must replay the failed proposer invocation through the mocked provider
    instead of re-raising the stale-envelope block.
    """
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, _artifacts, _failure, _route, _context = _seed_pre_attempt(
        factory, tmp_path, blocked=True
    )
    _seed_failed_proposer(factory, attempt_id)
    transport = _FakeAzureTransport([_responses_body(json.dumps(_proposal_candidate(app_ts)))])
    repair_service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )
    orchestrator = _orchestrator(factory, repair_service)
    continuations = TransformationContinuationService()

    session = factory()
    woken = continuations.wake(session, "cont-1")
    assert woken.status == "queued"
    session.commit()
    session.close()
    session = factory()
    claimed = continuations.claim_next(session, "worker-2", now=NOW + timedelta(seconds=300))
    assert claimed is not None
    assert claimed.current_node == "propose_repair"
    session.commit()
    session.close()

    orchestrator.advance("cont-1", "worker-2")

    session = factory()
    assert len(transport.calls) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "review_repair"
    assert continuation.worker_id is None
    assert continuation.lease_expires_at is None
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    assert invocations[0].id == f"{attempt_id}:proposer"
    assert invocations[0].status == "completed"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "proposed"
    assert attempt.proposal_artifact_id is not None
    session.close()
    engine.dispose()
