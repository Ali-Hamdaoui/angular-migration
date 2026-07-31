import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.llm_gateway import AzureGatewayError, LlmFailureCode
from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
    RepairLlmError,
    RepairReview,
    _translate_gateway_failure,
)


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


def test_reviewer_schema_cannot_author_candidate_content():
    with pytest.raises(ValidationError):
        RepairReview.model_validate(
            {
                "proposal_checksum": "sha256:proposal",
                "decision": "accept",
                "findings": [],
                "policy_checks": ["paths"],
                "risk_assessment": "low",
                "required_validation_targets": ["build"],
                "limitations": [],
                "operations": [{"operation": "replace_text"}],
            }
        )


def test_reviewer_schema_rejects_unified_diff_field():
    with pytest.raises(ValidationError):
        RepairReview.model_validate(
            {
                "proposal_checksum": "sha256:proposal",
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
