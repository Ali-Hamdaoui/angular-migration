import sys

sys.path.insert(0, "backend")

import pytest
from pydantic import ValidationError

from app.llm_gateway.azure_gateway import PromptSchemaRegistry
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
    for name in ("repair_proposer_v1", "repair_reviewer_v1"):
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
