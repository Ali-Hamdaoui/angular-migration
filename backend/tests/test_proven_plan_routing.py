"""Proven-plan routing contract: plan requests carry the semantic version,
the proven graph preserves the shared pre-G07 governance chain, and the
routing tables remain complete."""

import pytest
from types import SimpleNamespace

from app.api.planning_contracts import PlanCreateRequest
from app.domain.planning import (
    TRANSFORMER_SEMANTIC_VERSION_LEGACY,
    TRANSFORMER_SEMANTIC_VERSION_PROVEN,
)
from app.orchestration.transformer_graph import PROVEN_ROUTING, PROVEN_SHARED_ROUTING, TransformerOrchestrator

SHARED_GOVERNANCE = {
    "prepare_workspace",
    "resolve_runtime",
    "dependency_preflight",
    "collect_known_decisions",
    "create_g07",
}


def _request(**overrides):
    base = dict(
        expected_state_version=1,
        idempotency_key="routing-test",
        source_exact="11.2.14",
        source_family="angular-11.x",
        target_family="angular-12.x",
        catalogue_version="catalog-v4",
        input_fingerprint="sha256:" + "0" * 64,
        evidence_set_checksum="sha256:" + "0" * 64,
        execution_profile_id="runtime-node12",
        resolved_scripts={"build": "ng build", "test": "ng test"},
        project_targets={"project": "app", "build_target": "build"},
        stage_route=[("angular-11.x", "angular-12.x", "angular-11-to-12", "12.2.17", "12.2.18")],
        builder="@angular-devkit/build-angular",
        prerequisite_artifacts=[{"artifact_id": "artifact-a", "checksum": "sha256:" + "1" * 64}],
    )
    base.update(overrides)
    return PlanCreateRequest(**base)


def test_plan_create_request_defaults_to_legacy():
    request = _request()
    assert request.transformer_semantic_version == TRANSFORMER_SEMANTIC_VERSION_LEGACY


def test_plan_create_request_accepts_proven():
    request = _request(transformer_semantic_version=TRANSFORMER_SEMANTIC_VERSION_PROVEN)
    assert request.transformer_semantic_version == TRANSFORMER_SEMANTIC_VERSION_PROVEN


def test_proven_shared_routing_preserves_pre_g07_governance():
    missing = SHARED_GOVERNANCE - set(PROVEN_SHARED_ROUTING)
    assert not missing, f"proven graph skips shared governance nodes: {sorted(missing)}"


def test_proven_shared_handlers_exist_on_the_graph():
    graph = TransformerOrchestrator.__new__(TransformerOrchestrator)
    missing = [
        node for node, handler in PROVEN_SHARED_ROUTING.items() if not hasattr(graph, handler)
    ]
    assert not missing, f"shared routing references missing handlers: {missing}"


def test_proven_routing_table_still_covers_every_proven_node():
    from app.domain.transformation import PROVEN_TRANSITION_NODES

    assert PROVEN_TRANSITION_NODES.issubset(PROVEN_ROUTING)


def test_proven_validation_retry_uses_a_new_execution_key():
    from app.services.proven_stage_execution_service import ProvenStageExecutionService

    continuation = SimpleNamespace(
        attempt=2,
        last_error_code="FAILURE_ROUTE_ENVIRONMENT_TRANSIENT",
    )

    assert (
        ProvenStageExecutionService._validation_attempt_key(continuation, "validation_test")
        == "environment-retry:2:validation_test"
    )
