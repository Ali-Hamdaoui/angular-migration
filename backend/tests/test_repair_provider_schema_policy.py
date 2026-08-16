import sys

sys.path.insert(0, "backend")

import pytest
from pydantic import ValidationError

from app.llm_gateway.azure_gateway import (
    PRODUCTION_LLM_POLICY_TUPLES,
    PromptRegistry,
    PromptSchemaRegistry,
)
from app.services import repair_application_service
from app.services.repair_application_service import RepairProposal, RepairReview


UNSUPPORTED = {"minLength", "maxLength", "pattern", "format", "minimum", "maximum", "multipleOf", "minItems", "maxItems", "uniqueItems", "patternProperties", "unevaluatedProperties", "propertyNames"}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _registry() -> PromptSchemaRegistry:
    registry = PromptSchemaRegistry(version="test")
    registry.register("repair_proposer_v1", RepairProposal)
    registry.register("repair_reviewer_v1", RepairReview)
    registry.register(
        "repair_proposer_candidate_v2", repair_application_service.RepairProposalCandidate
    )
    registry.register(
        "repair_reviewer_candidate_v2", repair_application_service.RepairReviewCandidate
    )
    return registry


def _proposal(**overrides) -> dict[str, object]:
    value = {
        "failure_evidence_checksum": "sha256:" + "0" * 64,
        "context_pack_checksum": "sha256:" + "1" * 64,
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/main.ts",
                "preimage_sha256": None,
                "old_text": "old",
                "new_text": "new",
                "content": None,
            }
        ],
        "unified_diff": None,
        "touched_files": ["src/main.ts"],
        "rationale": ["reason"],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }
    value.update(overrides)
    return value


def _review(**overrides) -> dict[str, object]:
    value = {
        "proposal_checksum": "sha256:" + "0" * 64,
        "decision": "accept",
        "findings": [],
        "policy_checks": ["no commands"],
        "risk_assessment": "low risk",
        "required_validation_targets": ["build"],
        "limitations": [],
    }
    value.update(overrides)
    return value


def test_repair_provider_schemas_are_azure_strict_and_backend_bound():
    registry = _registry()
    for name in (
        "repair_proposer_v1",
        "repair_reviewer_v1",
        "repair_proposer_candidate_v2",
        "repair_reviewer_candidate_v2",
    ):
        schema = registry.json_schema(name)
        for node in _walk(schema):
            assert not UNSUPPORTED.intersection(node)
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))


def test_repair_azure_schemas_carry_enums_without_patterns():
    proposer = _registry().json_schema("repair_proposer_v1")
    operation = proposer["properties"]["operations"]["items"]["properties"]["operation"]
    assert operation["enum"] == [
        "replace_text",
        "create_text_file",
        "delete_text_file",
        "dependency_change",
    ]
    assert "pattern" not in operation
    assert proposer["properties"]["proposal_format"]["enum"] == ["operations", "unified_diff"]
    assert "pattern" not in proposer["properties"]["proposal_format"]
    assert proposer["properties"]["risk_level"]["enum"] == ["low", "medium", "high"]
    assert "pattern" not in proposer["properties"]["risk_level"]

    reviewer = _registry().json_schema("repair_reviewer_v1")
    assert reviewer["properties"]["decision"]["enum"] == ["accept", "request_changes", "reject"]
    assert "pattern" not in reviewer["properties"]["decision"]


def test_repair_local_models_reject_out_of_vocabulary_values():
    with pytest.raises(ValidationError):
        RepairProposal.model_validate(
            _proposal(
                operations=[
                    {
                        "operation": "modify_file",
                        "path": "src/main.ts",
                        "preimage_sha256": None,
                        "old_text": "old",
                        "new_text": "new",
                        "content": None,
                    }
                ]
            )
        )
    with pytest.raises(ValidationError):
        RepairProposal.model_validate(_proposal(proposal_format="diff"))
    with pytest.raises(ValidationError):
        RepairProposal.model_validate(_proposal(risk_level="critical"))
    with pytest.raises(ValidationError):
        RepairReview.model_validate(_review(decision="reject_all"))


def test_repair_valid_operations_and_unified_diff_proposals_validate():
    operations = RepairProposal.model_validate(_proposal())
    assert operations.proposal_format == "operations"
    assert operations.operations[0].operation == "replace_text"

    unified = RepairProposal.model_validate(
        _proposal(
            proposal_format="unified_diff",
            operations=[],
            unified_diff="--- a/src/main.ts\n+++ b/src/main.ts\n@@ -1 +1 @@\n-old\n+new\n",
        )
    )
    assert unified.proposal_format == "unified_diff"
    assert unified.unified_diff is not None

    review = RepairReview.model_validate(_review())
    assert review.decision == "accept"


def test_v2_candidate_models_reject_authority_and_arbitrary_fields():
    operation = {
        "operation": "replace_text",
        "path": "src/main.ts",
        "old_text": "old",
        "new_text": "new",
        "content": None,
    }
    proposal = {
        "proposal_format": "operations",
        "operations": [operation],
        "unified_diff": None,
        "rationale": ["reason"],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }
    review = {
        "decision": "accept",
        "findings": [],
        "policy_checks": ["no commands"],
        "risk_assessment": "low risk",
        "required_validation_targets": ["build"],
        "limitations": [],
    }
    forbidden = (
        (repair_application_service.RepairOperationCandidate, operation, "preimage_sha256"),
        (repair_application_service.RepairOperationCandidate, operation, "operation_id"),
        (repair_application_service.RepairOperationCandidate, operation, "preimage_fingerprint"),
        (repair_application_service.RepairOperationCandidate, operation, "apply_gate"),
        (repair_application_service.RepairOperationCandidate, operation, "command"),
        (repair_application_service.RepairOperationCandidate, operation, "status"),
        (repair_application_service.RepairProposalCandidate, proposal, "failure_evidence_checksum"),
        (repair_application_service.RepairProposalCandidate, proposal, "context_pack_checksum"),
        (repair_application_service.RepairProposalCandidate, proposal, "touched_files"),
        (repair_application_service.RepairProposalCandidate, proposal, "attempt_id"),
        (repair_application_service.RepairProposalCandidate, proposal, "workspace_fingerprint"),
        (repair_application_service.RepairProposalCandidate, proposal, "approval_gate"),
        (repair_application_service.RepairProposalCandidate, proposal, "command"),
        (repair_application_service.RepairProposalCandidate, proposal, "status"),
        (repair_application_service.RepairReviewCandidate, review, "proposal_checksum"),
        (repair_application_service.RepairReviewCandidate, review, "review_id"),
        (repair_application_service.RepairReviewCandidate, review, "proposal_fingerprint"),
        (repair_application_service.RepairReviewCandidate, review, "approval_gate"),
        (repair_application_service.RepairReviewCandidate, review, "command"),
        (repair_application_service.RepairReviewCandidate, review, "status"),
        (repair_application_service.RepairReviewCandidate, review, "arbitrary_extra"),
    )

    for model, payload, field in forbidden:
        with pytest.raises(ValidationError):
            model.model_validate({**payload, field: "authoritative"})


def test_v2_reviewer_candidate_cannot_author_operations_or_diff():
    review = {
        "decision": "accept",
        "findings": [],
        "policy_checks": ["no commands"],
        "risk_assessment": "low risk",
        "required_validation_targets": ["build"],
        "limitations": [],
    }

    for field, value in (
        ("operations", [{"operation": "replace_text"}]),
        ("unified_diff", "--- a/src/main.ts\n+++ b/src/main.ts\n"),
    ):
        with pytest.raises(ValidationError):
            repair_application_service.RepairReviewCandidate.model_validate({**review, field: value})


def test_v1_persisted_repair_payloads_remain_readable():
    assert RepairProposal.model_validate(_proposal()).failure_evidence_checksum.startswith("sha256:")
    assert RepairReview.model_validate(_review()).proposal_checksum.startswith("sha256:")


def test_v2_repair_candidate_registry_and_prompt_versions_exist():
    registry = _registry()
    assert registry.json_schema("repair_proposer_candidate_v2")["type"] == "object"
    assert registry.json_schema("repair_reviewer_candidate_v2")["type"] == "object"

    prompts = PromptRegistry.defaults()
    assert (
        prompts.get("repair_proposer_candidate_v2").version
        == "prompt-repair-proposer-candidate-v2"
    )
    assert (
        prompts.get("repair_reviewer_candidate_v2").version
        == "prompt-repair-reviewer-candidate-v2"
    )
    proposer_policy = prompts.get("repair_proposer_candidate_v2").system_policy
    assert 'package.json change must use proposal_format "operations"' in proposer_policy
    assert 'operation "dependency_change"' in proposer_policy
    assert "Never patch package-lock.json or npm-shrinkwrap.json directly" in proposer_policy
    assert ("repair_proposer_candidate_v2", repair_application_service.LlmTaskType.REPAIR_DIAGNOSIS) in PRODUCTION_LLM_POLICY_TUPLES
    assert ("repair_reviewer_candidate_v2", repair_application_service.LlmTaskType.REPAIR_REVIEW) in PRODUCTION_LLM_POLICY_TUPLES


def test_reviewer_policy_matches_backend_bound_dependency_transition_contract():
    policy = repair_application_service.REVIEWER_CAUSAL_POLICY
    assert "blocking_dependency" in policy
    assert "target_state" in policy
    assert "do not require operation-level" in policy
