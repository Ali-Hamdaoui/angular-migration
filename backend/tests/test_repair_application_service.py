import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
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
from app.llm_gateway.azure_gateway import ProviderTransportResult
from app.repositories.models import (
    ArtifactMetadataModel,
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services import repair_application_service
from app.services.causal_review import causal_rejection
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
    RepairLlmError,
    RepairProposal,
    RepairProposalCandidate,
    RepairReview,
    RepairReviewCandidate,
    _translate_gateway_failure,
)
from app.services.stage_preparation_primitives import StageSandboxCopier

NOW = datetime(2026, 7, 31, tzinfo=UTC)


def _proposal(path: Path):
    checksum = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "preimage_sha256": checksum,
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


def _proposal_candidate():
    return {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "old_text": "old",
                "new_text": "new",
                "content": None,
            }
        ],
        "unified_diff": None,
        "rationale": ["Fix the compiler error."],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }


def _review_candidate():
    return {
        "decision": "accept",
        "findings": [],
        "policy_checks": ["paths"],
        "risk_assessment": "low",
        "required_validation_targets": ["build"],
        "limitations": [],
    }


def _lockfile_generation_commands():
    return {
        "lockfile_generation": [
            {
                "command_id": "npm-lockfile-generate",
                "template_id": "tpl-npm-lockfile-generate",
                "template_version": 1,
                "parameter_bindings": {},
                "executable": "npm",
                "arguments": [
                    "install",
                    "--package-lock-only",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                ],
                "shell": False,
                "working_directory_alias": "STAGE_WORKSPACE_1",
                "timeout_seconds": 3600,
                "network_profile": "approved-registries-only",
                "runtime_profile_checksum": "sha256:" + "4" * 64,
                "cancellation_policy": "terminate_process_tree",
                "conditional": False,
            }
        ]
    }


def test_proposal_semantics_bind_preimage_and_safe_path(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")
    service = RepairApplicationService(scope=None)
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    assert service.validate_proposal(_proposal(target), context)["risk_level"] == "low"
    escaped = _proposal(target)
    escaped["operations"][0]["path"] = "../outside.ts"
    escaped["touched_files"] = ["../outside.ts"]
    with pytest.raises(RepairApplicationError, match="outside policy"):
        service.validate_proposal(escaped, context)


def test_dependency_change_requires_exact_stage_plan_authority(tmp_path: Path):
    package = tmp_path / "package.json"
    package.write_text('{"dependencies":{"x":"1.0.0"}}', encoding="utf-8")
    proposal = _proposal(package)
    proposal["operations"][0].update(
        {
            "operation": "dependency_change",
            "path": "package.json",
            "old_text": '"x":"1.0.0"',
            "new_text": '"x":"2.0.0"',
        }
    )
    proposal["touched_files"] = ["package.json"]
    context = {
        "workspace_path": str(tmp_path),
        "workspace_binding_alias": "STAGE_WORKSPACE_1",
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "stage_plan_commands": {},
    }
    service = RepairApplicationService(scope=None)

    with pytest.raises(RepairApplicationError) as error:
        service.validate_proposal(proposal, context)
    assert error.value.code == "STAGE_PLAN_COMMAND_AUTHORITY_MISSING"

    context["stage_plan_commands"] = _lockfile_generation_commands()
    assert service.validate_proposal(proposal, context)["operations"][0]["operation"] == (
        "dependency_change"
    )


def test_unified_diff_cannot_modify_package_json(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    candidate = _proposal_candidate()
    candidate.update(
        {
            "proposal_format": "unified_diff",
            "operations": [],
            "unified_diff": (
                "--- a/package.json\n+++ b/package.json\n@@ -1 +1 @@\n"
                "-{\"name\":\"fixture\"}\n+{\"name\":\"updated\"}\n"
            ),
        }
    )
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    with pytest.raises(RepairApplicationError) as error:
        RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)
    assert error.value.code == "REPAIR_DEPENDENCY_OPERATION_REQUIRED"


def test_reviewer_candidate_schema_cannot_author_candidate_content():
    with pytest.raises(ValidationError):
        repair_application_service.RepairReviewCandidate.model_validate(
            {
                "decision": "accept",
                "findings": [],
                "policy_checks": ["paths"],
                "risk_assessment": "low",
                "required_validation_targets": ["build"],
                "limitations": [],
                "operations": [{"operation": "replace_text"}],
            }
        )


def test_reviewer_candidate_schema_rejects_unified_diff_field():
    with pytest.raises(ValidationError):
        repair_application_service.RepairReviewCandidate.model_validate(
            {
                "decision": "accept",
                "findings": [],
                "policy_checks": ["paths"],
                "risk_assessment": "low",
                "required_validation_targets": ["build"],
                "limitations": [],
                "unified_diff": "--- a/src/app.ts\n+++ b/src/app.ts\n",
            }
        )


@pytest.mark.parametrize(
    "failure, expected_code, expected_retryable",
    [
        (
            AzureGatewayError(LlmFailureCode.AUTHORIZATION, "Prompt policy is not registered for this task."),
            "LLM_PROMPT_POLICY_MISSING",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.SCHEMA, "Response schema is not registered."),
            "LLM_SCHEMA_POLICY_MISSING",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.CONFIGURATION, "Azure OpenAI gateway is not fully configured."),
            "LLM_CONFIGURATION_INVALID",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.INVALID_REQUEST, "Azure OpenAI request failed.", provider_status=400),
            "LLM_PROVIDER_BAD_REQUEST",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.AUTHENTICATION, "Azure OpenAI request failed.", provider_status=401),
            "LLM_PROVIDER_AUTH",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.AUTHORIZATION, "Azure OpenAI request failed.", provider_status=403),
            "LLM_PROVIDER_AUTH",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.TIMEOUT, "Azure OpenAI request failed.", provider_status=408),
            "LLM_PROVIDER_TIMEOUT",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.RATE_LIMIT, "Azure OpenAI request failed.", provider_status=429),
            "LLM_PROVIDER_RATE_LIMIT",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.SERVER, "Azure OpenAI request failed.", provider_status=500),
            "LLM_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.SERVER, "Azure OpenAI request failed.", provider_status=502),
            "LLM_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.SERVER, "Azure OpenAI request failed.", provider_status=503),
            "LLM_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.SERVER, "Azure OpenAI request failed.", provider_status=504),
            "LLM_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.TIMEOUT, "Azure OpenAI request timed out."),
            "LLM_PROVIDER_TIMEOUT",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.TRANSPORT, "Azure OpenAI network request failed.", retryable=True),
            "LLM_TRANSPORT_FAILED",
            True,
        ),
    ],
)
def test_gateway_failure_translation_table(failure, expected_code, expected_retryable):
    translated = _translate_gateway_failure(failure)

    assert isinstance(translated, RepairLlmError)
    assert isinstance(translated, RepairApplicationError)
    assert translated.code == expected_code
    assert translated.retryable is expected_retryable
    assert translated.message == str(failure)
    assert translated.__cause__ is failure
    assert translated.provider_status == failure.provider_status
    assert translated.provider_request_id == failure.provider_request_id
    assert translated.failure_stage == failure.failure_stage
    assert translated.failure_subtype == failure.failure_subtype


def test_gateway_failure_translation_carries_provider_fields():
    failure = AzureGatewayError(
        LlmFailureCode.SERVER,
        "Azure OpenAI request failed.",
        retryable=True,
        provider_status=503,
        provider_request_id="azure-request-9",
        failure_stage="http_response",
        failure_subtype="HTTP_ERROR_ENVELOPE",
    )

    translated = _translate_gateway_failure(failure)

    assert translated.code == "LLM_PROVIDER_UNAVAILABLE"
    assert translated.retryable is True
    assert translated.provider_status == 503
    assert translated.provider_request_id == "azure-request-9"
    assert translated.failure_stage == "http_response"
    assert translated.failure_subtype == "HTTP_ERROR_ENVELOPE"


def test_proposal_rejects_stale_preimage_duplicate_paths_and_mixed_formats(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")
    service = RepairApplicationService(scope=None)
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    stale = _proposal(target)
    stale["operations"][0]["preimage_sha256"] = "sha256:stale"
    with pytest.raises(RepairApplicationError, match="preimage"):
        service.validate_proposal(stale, context)

    duplicate = _proposal(target)
    duplicate["touched_files"] = ["src/app.ts", "src/app.ts"]
    with pytest.raises(RepairApplicationError, match="unique"):
        service.validate_proposal(duplicate, context)

    mixed = _proposal(target)
    mixed["unified_diff"] = "--- a/src/app.ts\n+++ b/src/app.ts\n"
    with pytest.raises(RepairApplicationError, match="only operations"):
        service.validate_proposal(mixed, context)


def test_proposal_rejects_lockfiles_and_binary_targets(tmp_path: Path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{}", encoding="utf-8")
    binary = tmp_path / "src" / "image.bin"
    binary.parent.mkdir()
    binary.write_bytes(b"\xff\xfe")
    service = RepairApplicationService(scope=None)
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    lock_proposal = _proposal(lockfile)
    lock_proposal["operations"][0]["path"] = "package-lock.json"
    lock_proposal["touched_files"] = ["package-lock.json"]
    with pytest.raises(RepairApplicationError, match="outside policy"):
        service.validate_proposal(lock_proposal, context)

    binary_proposal = _proposal(binary)
    binary_proposal["operations"][0]["path"] = "src/image.bin"
    binary_proposal["operations"][0]["preimage_sha256"] = (
        "sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    binary_proposal["touched_files"] = ["src/image.bin"]
    with pytest.raises(RepairApplicationError, match="UTF-8"):
        service.validate_proposal(binary_proposal, context)


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'service.db'}")
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


class _RecordingTransport:
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


def _gateway(transport, settings: Settings):
    schema_registry = PromptSchemaRegistry(version=settings.llm_schema_registry_version)
    schema_registry.register("repair_proposer_v1", RepairProposal)
    schema_registry.register("repair_reviewer_v1", RepairReview)
    schema_registry.register("repair_proposer_candidate_v2", RepairProposalCandidate)
    schema_registry.register("repair_reviewer_candidate_v2", RepairReviewCandidate)
    return AzureOpenAILLMGateway(
        settings=settings,
        transport=transport,
        registry=schema_registry,
        prompt_registry=PromptRegistry.defaults(),
    )


def _seed_service(factory, tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    app_ts = workspace / "src" / "app.ts"
    app_ts.write_text("old", encoding="utf-8")
    (workspace / "package.json").write_text('{"name": "fixture"}', encoding="utf-8")
    (workspace / "angular.json").write_text('{"project": "fixture"}', encoding="utf-8")
    (workspace / "tsconfig.json").write_text('{"compilerOptions": {}}', encoding="utf-8")
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    attempt_id = "repair-1"
    failure = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/failure-evidence.json",
        json.dumps({"attempt_id": attempt_id, "failure": "compiler", "stage_id": "stage-1"}),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-failure-evidence",
        created_at=NOW,
    )
    evidence = {
        "schema_version": "transformer-failure-evidence-v1",
        "run_id": "run-1",
        "stage_id": "stage-1",
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
        "failure_fingerprint": "fingerprint-failure",
        "prior_fingerprints": [],
        "repair_policy": {},
        "forbidden_change_policy": {},
    }
    context = FailureEvidenceService().write_context_pack(evidence, failure.ref.checksum)
    session = factory()
    run = MigrationRunModel(
        id="run-1",
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
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=StageSandboxCopier.fingerprint(workspace),
        fingerprint_profile_id=repair_application_service.STAGE_FINGERPRINT_PROFILE.profile_id,
        active=True,
        created_at=NOW,
    )
    plan = StageExecutionPlanModel(
        id="stage-plan-stage-1", run_id="run-1", migration_plan_id="plan-1", stage_id="stage-1",
        idempotency_key="plan", request_checksum="sha256:plan", actor="operator",
        correlation_id="corr-1", status="approved", version=1,
        stage_plan={"repair_policy": {"max_attempts": 3}}, checksum="sha256:stage-plan",
        artifact_ids=[], artifact_checksums={}, state_version=1, event_sequence=1,
        created_at=NOW, updated_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1", run_id="run-1", current_stage_id="stage-1", thread_id="thread-1",
        status="running", current_node="propose_repair", g06_approval_id="g06-1",
        plan_id="plan-1", plan_checksum="sha256:plan", stage_plan_id=plan.id,
        stage_plan_checksum=plan.checksum, worker_id="worker-1", attempt=1, max_attempts=3,
        lease_expires_at=NOW, idempotency_key="continuation", request_checksum="sha256:continuation",
        state_version=3, created_at=NOW, updated_at=NOW,
    )
    attempt = RepairAttemptModel(
        id=attempt_id,
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=1,
        status="evidence_frozen",
        risk_level="unknown",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        checkpoint_id="ckpt-pre",
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id="artifact-route",
        failure_route_checksum="sha256:route",
        context_pack_artifact_id=context.ref.artifact_id,
        context_pack_checksum=context.ref.checksum,
        proposal_artifact_id=None,
        proposal_checksum=None,
        proposer_invocation_id=None,
        pre_fingerprint=context.ref.checksum,
        failure_fingerprint="fingerprint-failure",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, plan, binding, continuation, attempt])
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + failure.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
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
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=context.ref.artifact_type.value,
            relative_path=context.ref.relative_path,
            checksum=context.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.commit()
    session.close()
    return store, attempt_id, app_ts, artifacts


def _seed_failed_v1_invocation(factory, attempt_id: str):
    session = factory()
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id="run-1",
            stage_id="stage-1",
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


def test_proposer_candidate_schema_rejects_backend_authority_fields():
    for field, value in (
        ("failure_evidence_checksum", "sha256:attacker"),
        ("context_pack_checksum", "sha256:attacker"),
        ("touched_files", ["src/other.ts"]),
        ("command", "npm test"),
    ):
        with pytest.raises(ValidationError):
            RepairProposalCandidate.model_validate({**_proposal_candidate(), field: value})

    operation = _proposal_candidate()
    operation["operations"][0]["preimage_sha256"] = "sha256:attacker"
    with pytest.raises(ValidationError):
        RepairProposalCandidate.model_validate(operation)


def test_propose_persists_failed_row_for_schema_failure_after_transport(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    out_of_vocabulary = _proposal_candidate()
    out_of_vocabulary["operations"] = [{"operation": "modify_file", "path": "src/app.ts"}]
    body = _responses_body(json.dumps(out_of_vocabulary))
    transport = _RecordingTransport(
        [
            ProviderTransportResult(
                body=body,
                provider_request_id="azure-request-schema-1",
                provider_status=200,
                response_content_type="application/json",
                response_bytes=len(json.dumps(body)),
                response_sha256=hashlib.sha256(json.dumps(body).encode()).hexdigest(),
                response_kind="json",
            )
        ]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairLlmError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert len(transport.calls) == 1
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.idempotency_key == f"{attempt_id}:proposer"
    assert invocation.status == "failed"
    assert invocation.failure_code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert invocation.failure_stage == "schema_validation"
    assert invocation.transport_started is True
    assert invocation.response_received is True
    assert invocation.provider_request_id == "azure-request-schema-1"
    assert invocation.provider_http_status == 200
    assert invocation.response_sha256 is not None
    session.close()
    engine.dispose()


def test_repair_runtime_uses_v2_candidates_and_binds_authority_fields(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, _artifacts = _seed_service(factory, tmp_path)
    transport = _RecordingTransport(
        [
            _responses_body(json.dumps(_proposal_candidate())),
            _responses_body(json.dumps(_review_candidate())),
        ]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    proposal = service.propose(attempt_id)
    review = service.review(attempt_id)

    formats = [call["payload"]["text"]["format"] for call in transport.calls]
    assert [item["name"] for item in formats] == [
        "repair_proposer_candidate_v2",
        "repair_reviewer_candidate_v2",
    ]
    assert "failure_evidence_checksum" not in formats[0]["schema"]["properties"]
    assert "proposal_checksum" not in formats[1]["schema"]["properties"]
    session = factory()
    assert proposal["failure_evidence_checksum"] == session.get(RepairAttemptModel, attempt_id).failure_evidence_checksum
    assert proposal["context_pack_checksum"] == session.get(RepairAttemptModel, attempt_id).context_pack_checksum
    session.close()
    assert proposal["touched_files"] == ["src/app.ts"]
    assert proposal["operations"][0]["preimage_sha256"] == (
        "sha256:" + hashlib.sha256(app_ts.read_bytes()).hexdigest()
    )

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    invocations = {item.id: item for item in session.query(LlmInvocationModel).all()}
    assert review["proposal_checksum"] == attempt.proposal_checksum
    assert invocations[f"{attempt_id}:proposer"].prompt_version == (
        "prompt-repair-proposer-candidate-v2"
    )
    assert invocations[f"{attempt_id}:reviewer"].prompt_version == (
        "prompt-repair-reviewer-candidate-v2"
    )
    assert invocations[f"{attempt_id}:proposer"].schema_version == "schema-registry-v1"
    assert invocations[f"{attempt_id}:reviewer"].schema_version == "schema-registry-v1"
    session.close()
    engine.dispose()


def test_repair_runtime_binds_unified_diff_touched_files(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    proposal = _proposal_candidate()
    proposal.update(
        {
            "proposal_format": "unified_diff",
            "operations": [],
            "unified_diff": "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n--- text\n+++ text\n",
        }
    )
    transport = _RecordingTransport([_responses_body(json.dumps(proposal))])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    bound = service.propose(attempt_id)

    assert bound["operations"] == []
    assert bound["touched_files"] == ["src/app.ts"]
    engine.dispose()


def test_repair_runtime_rejects_incomplete_unified_diff_hunk(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    proposal = _proposal_candidate()
    proposal.update(
        {
            "proposal_format": "unified_diff",
            "operations": [],
            "unified_diff": "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1,2 +1,2 @@\n-old\n+new\n",
        }
    )
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport([_responses_body(json.dumps(proposal))]),
            _azure_settings(tmp_path),
        ),
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_DIFF_INVALID"
    assert not (artifacts / f"05_repairs/attempt-{attempt_id}/proposal.json").exists()
    engine.dispose()


@pytest.mark.parametrize(
    ("unified_diff", "expected_code"),
    [
        (
            "+++ b/src/app.ts\n@@ -1 +1 @@\n-old\n+new\n",
            "REPAIR_DIFF_INVALID",
        ),
        (
            "--- /forbidden\n+++ b/src/app.ts\n@@ -1 +1 @@\n-old\n+new\n",
            "REPAIR_PATH_FORBIDDEN",
        ),
    ],
)
def test_unified_diff_requires_safe_paired_headers(
    tmp_path: Path, unified_diff: str, expected_code: str
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    candidate = _proposal_candidate()
    candidate.update(
        {
            "proposal_format": "unified_diff",
            "operations": [],
            "unified_diff": unified_diff,
        }
    )
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport([_responses_body(json.dumps(candidate))]),
            _azure_settings(tmp_path),
        ),
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == expected_code
    session = factory()
    assert session.get(RepairAttemptModel, attempt_id).proposal_artifact_id is None
    session.close()
    engine.dispose()


@pytest.mark.parametrize("proposal_format", ["operations", "unified_diff"])
def test_candidate_binding_canonicalizes_paths_targets_and_preimages(
    tmp_path: Path, proposal_format: str
):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")
    candidate = _proposal_candidate()
    candidate["validation_targets"] = ["build", "test", "build"]
    if proposal_format == "operations":
        candidate["operations"][0]["path"] = "src/./app.ts"
    else:
        candidate.update(
            {
                "proposal_format": "unified_diff",
                "operations": [],
                "unified_diff": "--- a/src/./app.ts\n+++ b/src/./app.ts\n@@ -1 +1 @@\n-old\n+new\n",
            }
        )
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:attempt-failure",
        "context_pack_checksum": "sha256:attempt-context",
    }

    bound = RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)

    assert bound["failure_evidence_checksum"] == "sha256:attempt-failure"
    assert bound["context_pack_checksum"] == "sha256:attempt-context"
    assert bound["touched_files"] == ["src/app.ts"]
    assert bound["validation_targets"] == ["build", "test"]
    if proposal_format == "operations":
        assert bound["operations"][0]["path"] == "src/app.ts"
        assert bound["operations"][0]["preimage_sha256"] == (
            "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
        )


def test_unknown_proposer_target_persists_only_linked_failure_artifact(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    candidate = _proposal_candidate()
    candidate["validation_targets"] = ["deploy"]
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport([_responses_body(json.dumps(candidate))]),
            _azure_settings(tmp_path),
        ),
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "LLM_SCHEMA_VALIDATION_FAILED"
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    assert attempt.proposal_artifact_id is None
    assert len(invocation.artifact_ids) == 1
    assert invocation.artifact_checksums == {
        invocation.artifact_ids[0]: session.get(
            ArtifactMetadataModel, "metadata-" + invocation.artifact_ids[0]
        ).checksum
    }
    session.close()
    inventory = {
        path.name for path in (artifacts / "05_repairs" / f"attempt-{attempt_id}").glob("*.json")
    }
    assert "proposal.json" not in inventory
    assert "propose-error.json" in inventory
    engine.dispose()


def test_failed_replay_retains_all_immutable_failure_artifact_links(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    candidate = _proposal_candidate()
    candidate["validation_targets"] = ["deploy"]
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport(
                [
                    _responses_body(json.dumps(candidate)),
                    _responses_body(json.dumps(candidate)),
                ]
            ),
            _azure_settings(tmp_path),
        ),
    )

    for _ in range(2):
        with pytest.raises(RepairApplicationError) as raised:
            service.propose(attempt_id)
        assert raised.value.code == "LLM_SCHEMA_VALIDATION_FAILED"

    session = factory()
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    assert len(invocation.artifact_ids) == 2
    assert len(set(invocation.artifact_ids)) == 2
    assert set(invocation.artifact_checksums) == set(invocation.artifact_ids)
    assert {
        session.get(ArtifactMetadataModel, "metadata-" + artifact_id).relative_path
        for artifact_id in invocation.artifact_ids
    } == {
        f"05_repairs/attempt-{attempt_id}/propose-error.json",
        f"05_repairs/attempt-{attempt_id}/propose-error__v2.json",
    }
    session.close()
    engine.dispose()


def test_failed_then_successful_proposer_replay_retains_failure_evidence(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    invalid = _proposal_candidate()
    invalid["validation_targets"] = ["deploy"]
    valid = _proposal_candidate()
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport(
                [_responses_body(json.dumps(invalid)), _responses_body(json.dumps(valid))]
            ),
            _azure_settings(tmp_path),
        ),
    )

    with pytest.raises(RepairApplicationError):
        service.propose(attempt_id)
    proposal = service.propose(attempt_id)
    assert service.propose(attempt_id) == proposal

    session = factory()
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    assert len(invocation.artifact_ids) == 2
    assert set(invocation.artifact_checksums) == set(invocation.artifact_ids)
    assert {
        session.get(ArtifactMetadataModel, "metadata-" + artifact_id).relative_path
        for artifact_id in invocation.artifact_ids
    } == {
        f"05_repairs/attempt-{attempt_id}/propose-error.json",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
    }
    session.close()
    engine.dispose()


def test_unknown_reviewer_target_persists_no_review_artifact(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    review = _review_candidate()
    review["required_validation_targets"] = ["deploy"]
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport(
                [
                    _responses_body(json.dumps(_proposal_candidate())),
                    _responses_body(json.dumps(review)),
                ]
            ),
            _azure_settings(tmp_path),
        ),
    )
    service.propose(attempt_id)

    with pytest.raises(RepairApplicationError) as raised:
        service.review(attempt_id)

    assert raised.value.code == "LLM_SCHEMA_VALIDATION_FAILED"
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:reviewer")
    assert attempt.review_artifact_id is None
    assert len(invocation.artifact_ids) == 1
    session.close()
    inventory = {
        path.name for path in (artifacts / "05_repairs" / f"attempt-{attempt_id}").glob("*.json")
    }
    assert "review.json" not in inventory
    assert "review-error.json" in inventory
    engine.dispose()


def test_review_binds_immutable_active_proposal_artifact_checksum(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    transport = _RecordingTransport([
        _responses_body(json.dumps(_proposal_candidate())),
        _responses_body(json.dumps(_review_candidate())),
    ])
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )
    service.propose(attempt_id)
    calls_before_review = len(transport.calls)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.proposal_checksum = "sha256:stale-row-value"
    session.commit()
    session.close()

    with pytest.raises(RepairApplicationError) as raised:
        service.review(attempt_id)
    assert raised.value.code == "REPAIR_ARTIFACT_RECOVERY_FAILED"
    assert len(transport.calls) == calls_before_review

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.review_artifact_id is None
    assert session.get(LlmInvocationModel, f"{attempt_id}:reviewer") is None
    session.close()
    inventory = {
        path.name for path in (artifacts / "05_repairs" / f"attempt-{attempt_id}").glob("*.json")
    }
    assert "review.json" not in inventory
    engine.dispose()

def test_v1_persisted_proposal_and_review_artifacts_still_recover(tmp_path: Path):
    engine, factory = _database(tmp_path)
    store, attempt_id, app_ts, artifacts = _seed_service(factory, tmp_path)
    session = factory()
    seeded_attempt = session.get(RepairAttemptModel, attempt_id)
    proposal_payload = _proposal(app_ts)
    proposal_payload["failure_evidence_checksum"] = seeded_attempt.failure_evidence_checksum
    proposal_payload["context_pack_checksum"] = seeded_attempt.context_pack_checksum
    session.close()
    proposal = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(proposal_payload),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-proposal-v1",
        created_at=NOW,
    )
    review_payload = {
        "proposal_checksum": proposal.ref.checksum,
        "decision": "accept",
        "findings": [],
        "policy_checks": ["paths"],
        "risk_assessment": "low",
        "required_validation_targets": ["build"],
        "limitations": [],
    }
    review = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/review.json",
        json.dumps(review_payload),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-review-v1",
        created_at=NOW,
    )
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.proposal_artifact_id = proposal.ref.artifact_id
    attempt.proposal_checksum = proposal.ref.checksum
    attempt.review_artifact_id = review.ref.artifact_id
    attempt.review_checksum = review.ref.checksum
    for role, stored in (("proposer", proposal), ("reviewer", review)):
        session.add(
            LlmInvocationModel(
                id=f"{attempt_id}:{role}",
                run_id="run-1",
                stage_id="stage-1",
                idempotency_key=f"{attempt_id}:{role}",
                request_checksum="sha256:v1-request",
                input_hashes=[attempt.failure_evidence_checksum, attempt.context_pack_checksum],
                correlation_id=f"{attempt_id}:{role}",
                actor="transformer",
                role=f"repair_{role}",
                task_type="repair_diagnosis" if role == "proposer" else "repair_review",
                provider="azure_openai",
                deployment_alias="azure-openai",
                prompt_version=f"repair-{role}-v1",
                schema_version="schema-registry-v1",
                pricing_version="mvp-pricing-2026-01",
                stage="repair",
                status="completed",
                artifact_ids=[stored.ref.artifact_id],
                artifact_checksums={stored.ref.artifact_id: stored.ref.checksum},
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
                id="metadata-" + stored.ref.artifact_id,
                run_id="run-1",
                stage_id="stage-1",
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
    context = {
        "attempt_id": attempt_id,
        "run_id": "run-1",
        "stage_id": "stage-1",
        "artifact_root": str(artifacts),
    }
    service = RepairApplicationService(scope=_scope(factory))

    assert service._recover_completed(context, role="proposer") == proposal_payload
    assert service._recover_completed(context, role="reviewer") == review_payload
    engine.dispose()


def test_replayed_v1_invocation_refreshes_v2_provenance_for_success_and_failure(
    tmp_path: Path, monkeypatch
):
    for name, response, expected_status in (
        ("success", _responses_body(json.dumps(_proposal_candidate())), "completed"),
        (
            "failure",
            AzureGatewayError(LlmFailureCode.INVALID_REQUEST, "Azure OpenAI request failed."),
            "failed",
        ),
    ):
        case_path = tmp_path / name
        case_path.mkdir()
        engine, factory = _database(case_path)
        _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, case_path)
        _seed_failed_v1_invocation(factory, attempt_id)
        settings = _azure_settings(case_path).model_copy(
            update={"llm_schema_registry_version": "repair-schema-registry-v2"}
        )
        monkeypatch.setattr("app.services.repair_application_service.get_settings", lambda: settings)
        service = RepairApplicationService(
            scope=_scope(factory), gateway=_gateway(_RecordingTransport([response]), settings)
        )

        if expected_status == "completed":
            service.propose(attempt_id)
        else:
            with pytest.raises(RepairLlmError):
                service.propose(attempt_id)

        session = factory()
        invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
        assert invocation.status == expected_status
        assert invocation.prompt_version == "prompt-repair-proposer-candidate-v2"
        assert invocation.schema_version == "repair-schema-registry-v2"
        attempt = session.get(RepairAttemptModel, attempt_id)
        assert invocation.input_hashes[:2] == [attempt.failure_evidence_checksum, attempt.context_pack_checksum]
        assert invocation.input_hashes[2].startswith("schema:")
        assert "legacy" not in " ".join(invocation.input_hashes)
        session.close()
        engine.dispose()


def test_pre_transport_disabled_failure_persists_without_transport(tmp_path: Path, monkeypatch):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    disabled = _azure_settings(tmp_path).model_copy(update={"llm_enabled": False})
    monkeypatch.setattr(
        "app.services.repair_application_service.get_settings", lambda: disabled
    )
    service = RepairApplicationService(scope=_scope(factory), gateway=None)

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_LLM_DISABLED"
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.status == "failed"
    assert invocation.failure_code == "REPAIR_LLM_DISABLED"
    assert invocation.failure_stage == "local"
    assert invocation.transport_started is False
    assert invocation.response_received is False
    assert invocation.provider_request_id is None
    assert invocation.provider_http_status is None
    assert invocation.response_sha256 is None
    assert invocation.prompt_version == "prompt-repair-proposer-candidate-v2"
    assert invocation.schema_version == "schema-registry-v1"
    session.close()
    engine.dispose()


def test_semantic_failure_persists_repair_semantics_stage_without_proposal_artifact(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, artifacts = _seed_service(factory, tmp_path)
    mixed = _proposal_candidate()
    mixed["unified_diff"] = "--- a/src/app.ts\n+++ b/src/app.ts\n"
    transport = _RecordingTransport([_responses_body(json.dumps(mixed))])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_PROPOSAL_FORMAT_INVALID"
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.status == "failed"
    assert invocation.failure_code == "REPAIR_PROPOSAL_FORMAT_INVALID"
    assert invocation.failure_stage == "repair_semantics"
    assert invocation.transport_started is True
    assert invocation.response_received is True
    assert invocation.provider_request_id is None
    assert invocation.provider_http_status is None
    session.close()
    inventory = sorted(
        str(path.relative_to(artifacts)).replace("\\", "/")
        for path in artifacts.rglob("*")
        if path.is_file()
    )
    assert f"05_repairs/attempt-{attempt_id}/proposal.json" not in inventory
    assert f"05_repairs/attempt-{attempt_id}/propose-error.json" in inventory
    engine.dispose()


def test_recover_completed_failed_returns_none_and_uncertain_transport_raises(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    context = {
        "attempt_id": attempt_id,
        "run_id": "run-1",
        "stage_id": "stage-1",
        "artifact_root": str(artifacts),
    }
    session = factory()
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key=f"{attempt_id}:proposer",
            request_checksum="sha256:request",
            input_hashes=["sha256:failure", "sha256:context"],
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
            status="failed",
            failure_code="LLM_PROVIDER_BAD_REQUEST",
            artifact_ids=[],
            artifact_checksums={},
            state_version=1,
            event_sequence=0,
            retries=0,
            started_at=NOW,
            created_at=NOW,
        )
    )
    session.commit()
    session.close()
    service = RepairApplicationService(scope=_scope(factory))

    assert service._recover_completed(context, role="proposer") is None

    session = factory()
    invocation = session.query(LlmInvocationModel).one()
    invocation.status = "in_progress"
    invocation.transport_started = True
    session.commit()
    session.close()
    with pytest.raises(RepairApplicationError) as raised:
        service._recover_completed(context, role="proposer")
    assert raised.value.code == "REPAIR_INVOCATION_UNCERTAIN"
    engine.dispose()


def test_child_attempt_authority_snapshot_binds_parent_review_lineage(tmp_path: Path):
    """A child attempt's authority snapshot durably carries the parent review refs.

    RED until the fix: parent_review_artifact_id/parent_review_checksum are not
    part of the context or the authority snapshot, and a tampered parent review
    reference is not detected by the fresh-authority re-read.
    """
    engine, factory = _database(tmp_path)
    store, attempt_id, app_ts, _artifacts = _seed_service(factory, tmp_path)
    proposal = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(_proposal(app_ts), sort_keys=True),
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
    attempt.parent_attempt_id = "repair-parent"
    attempt.parent_review_artifact_id = "artifact-parent-review"
    attempt.parent_review_checksum = "sha256:parent-review"
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

    service = RepairApplicationService(scope=_scope(factory))
    context = service._attempt_context(attempt_id, include_proposal=True)
    assert context["parent_review_artifact_id"] == "artifact-parent-review"
    assert context["parent_review_checksum"] == "sha256:parent-review"
    assert context["authority_snapshot"]["parent_review_artifact_id"] == "artifact-parent-review"
    assert context["authority_snapshot"]["parent_review_checksum"] == "sha256:parent-review"

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.parent_review_checksum = "sha256:tampered"
    session.commit()
    session.close()
    with pytest.raises(RepairApplicationError) as raised:
        service._assert_fresh_authority(context, role="reviewer", include_proposal=True)
    assert raised.value.code == "REPAIR_REVIEW_STALE"
    engine.dispose()


def _tamper_context_pack(artifacts: Path, factory, *, mutate, sort_keys: bool = True) -> None:
    """Rewrite the bound context pack keeping envelope/metadata checksums consistent."""
    session = factory()
    attempt = session.get(RepairAttemptModel, "repair-1")
    row = session.get(ArtifactMetadataModel, "metadata-" + attempt.context_pack_artifact_id)
    relative_path = row.relative_path
    session.close()
    context_path = artifacts / relative_path
    payload = json.loads(context_path.read_text(encoding="utf-8"))
    mutate(payload)
    context_path.write_text(
        json.dumps(payload, indent=2, sort_keys=sort_keys), encoding="utf-8"
    )
    content_hash = "sha256:" + hashlib.sha256(context_path.read_bytes()).hexdigest()
    sidecar = artifacts / f"{relative_path}.meta.json"
    envelope = json.loads(sidecar.read_text(encoding="utf-8"))
    envelope["content_hash"] = content_hash
    sidecar.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
    session = factory()
    row = session.get(ArtifactMetadataModel, row.id)
    row.checksum = content_hash
    attempt = session.get(RepairAttemptModel, "repair-1")
    attempt.context_pack_checksum = content_hash
    session.commit()
    session.close()


def _reorder_file_excerpts(payload) -> None:
    entries = payload["file_excerpts"]
    first = entries.pop("package.json")
    payload["file_excerpts"] = {"package.json": first, **entries}


@pytest.mark.parametrize(
    "mutate, sort_keys",
    [
        (
            lambda payload: payload["file_excerpts"]["package.json"].update(
                {"sha256": "sha256:" + "0" * 64}
            ),
            True,
        ),
        (
            lambda payload: payload["file_excerpts"]["package.json"].update({"size_bytes": 0}),
            True,
        ),
        (lambda payload: payload["bounds"].update({"max_total_bytes": 1}), True),
        (_reorder_file_excerpts, False),
    ],
)
def test_tampered_context_pack_rejected_at_use_time(tmp_path: Path, mutate, sort_keys):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    _tamper_context_pack(artifacts, factory, mutate=mutate, sort_keys=sort_keys)
    transport = _RecordingTransport([])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_CONTEXT_INVALID"
    assert transport.calls == []
    session = factory()
    assert session.query(LlmInvocationModel).count() == 0
    session.close()
    engine.dispose()


def _force_evidence() -> dict:
    return {
        "normalized_failure": {
            "error_code": "DEPENDENCY_PREFLIGHT_BLOCKED",
            "failure_message": "npm ERR! ERESOLVE unable to resolve dependency tree",
            "failure_diagnosis": {
                "kind": "peer_dependency_conflict",
                "package": "@angular/core",
                "required_ranges": ["^19.0.0"],
            },
        }
    }


def _generic_executable_evidence() -> dict:
    return {
        "normalized_failure": {
            "error_code": "BUILD_FAILED",
            "failure_message": "TypeScript compilation failed",
        }
    }


def _transition_operation(**overrides) -> dict:
    operation = {
        "operation": "dependency_transition",
        "path": "package.json",
        "strategy": "detach_update_reattach",
        "repair_kind": "dependency_transition",
        "blocking_dependency": {"package": "@angular/core", "version": "18.2.0"},
        "target_state": {"package": "@angular/core", "target_major": 19},
    }
    operation.update(overrides)
    return operation


def test_causal_force_check_ignores_force_mention_in_rationale() -> None:
    proposal = {
        "operations": [_transition_operation()],
        "rationale": ["This repair does not bypass forbidden policies (for example using --force)"],
        "limitations": [],
    }
    assert causal_rejection(_force_evidence(), proposal) is None


def test_causal_force_check_ignores_force_mention_in_limitations() -> None:
    proposal = {
        "operations": [_transition_operation()],
        "rationale": ["Complete dependency transition"],
        "limitations": ["This sequence avoids using --force"],
    }
    assert causal_rejection(_force_evidence(), proposal) is None


def test_causal_force_check_rejects_executable_force_in_operation() -> None:
    proposal = {
        "operations": [
            {
                "operation": "replace_text",
                "path": "package.json",
                "new_text": "npm install --force",
                "old_text": "old",
            }
        ],
        "rationale": ["Update dependencies"],
        "limitations": [],
    }
    rejection = causal_rejection(_force_evidence(), proposal)
    assert rejection is not None
    assert rejection.code == "CAUSAL_REJECTION_FORCE"


def test_causal_force_check_allows_removing_force_via_replace_text() -> None:
    proposal = {
        "operations": [
            {
                "operation": "replace_text",
                "path": "package.json",
                "old_text": "ng update --force",
                "new_text": "ng update",
            }
        ],
        "rationale": ["Drop the --force flag"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_force_check_rejects_force_introduced_in_new_text() -> None:
    proposal = {
        "operations": [
            {
                "operation": "replace_text",
                "path": "package.json",
                "old_text": "ng update",
                "new_text": "ng update --force",
            }
        ],
        "rationale": ["Update dependencies"],
        "limitations": [],
    }
    rejection = causal_rejection(_generic_executable_evidence(), proposal)
    assert rejection is not None
    assert rejection.code == "CAUSAL_REJECTION_FORCE"


def test_causal_force_check_allows_diff_removing_force() -> None:
    proposal = {
        "operations": [],
        "touched_files": ["package.json"],
        "unified_diff": (
            "--- a/package.json\n"
            "+++ b/package.json\n"
            "@@ -1,3 +1,3 @@\n"
            ' "scripts": {\n'
            '-  "migrate": "ng update --force"\n'
            '+  "migrate": "ng update"\n'
            ' }'
        ),
        "rationale": ["Remove --force from the migrate script"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_force_check_rejects_diff_adding_force() -> None:
    proposal = {
        "operations": [],
        "touched_files": ["package.json"],
        "unified_diff": (
            "--- a/package.json\n"
            "+++ b/package.json\n"
            "@@ -1,3 +1,3 @@\n"
            ' "scripts": {\n'
            '-  "migrate": "ng update"\n'
            '+  "migrate": "ng update --force"\n'
            ' }'
        ),
        "rationale": ["Update dependencies"],
        "limitations": [],
    }
    rejection = causal_rejection(_generic_executable_evidence(), proposal)
    assert rejection is not None
    assert rejection.code == "CAUSAL_REJECTION_FORCE"


def test_causal_force_check_allows_source_comment_mentioning_force() -> None:
    proposal = {
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app/example.ts",
                "old_text": "// old",
                "new_text": "// never use --force during Angular migration",
            }
        ],
        "rationale": ["Add a migration note"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_force_check_allows_documentation_content_mentioning_force() -> None:
    proposal = {
        "operations": [
            {
                "operation": "create_text_file",
                "path": "docs/usage-guide",
                "content": "Do not use ng update --force during the migration",
            }
        ],
        "rationale": ["Document the migration policy"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_force_check_allows_diff_comment_mentioning_force() -> None:
    proposal = {
        "operations": [],
        "touched_files": ["src/app/example.ts"],
        "unified_diff": (
            "--- a/src/app/example.ts\n"
            "+++ b/src/app/example.ts\n"
            "@@ -1,3 +1,3 @@\n"
            ' "migrate": "ng update"\n'
            "+ // Never use --force here\n"
        ),
        "rationale": ["Add a comment"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_dependency_transition_validation_unchanged() -> None:
    proposal = {
        "operations": [_transition_operation()],
        "rationale": ["Complete dependency transition"],
        "limitations": [],
    }
    assert causal_rejection(_force_evidence(), proposal) is None
