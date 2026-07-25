import sys

sys.path.insert(0, "backend")

from app.llm_gateway.azure_gateway import PromptSchemaRegistry
from app.services.analysis_application_service import AnalysisGatewayNarrative, AnalysisGatewayReview


UNSUPPORTED = {"minLength", "maxLength", "pattern", "format", "minimum", "maximum", "multipleOf", "minItems", "maxItems", "uniqueItems", "patternProperties", "unevaluatedProperties", "propertyNames"}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_analysis_provider_schemas_are_azure_strict_and_backend_bound():
    registry = PromptSchemaRegistry(version="test")
    registry.register("proposer", AnalysisGatewayNarrative)
    registry.register("reviewer", AnalysisGatewayReview)
    for name in ("proposer", "reviewer"):
        schema = registry.json_schema(name)
        for node in _walk(schema):
            assert not UNSUPPORTED.intersection(node)
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))

    proposer = registry.json_schema("proposer")
    assert "deterministic_input_checksum" not in proposer["properties"]
    assert "proposer_output_checksum" not in registry.json_schema("reviewer")["properties"]
