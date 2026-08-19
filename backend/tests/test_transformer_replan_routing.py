from app.orchestration.transformer_graph import TransformerOrchestrator


class _Session:
    def __init__(self, intelligence):
        self.intelligence = intelligence

    def scalar(self, _query):
        return self.intelligence


class _Continuation:
    run_id = "run-routing"


def test_transformer_replan_route_requires_durable_dependency_intelligence():
    evidence = {
        "normalized_failure": {
            "error_code": "DEPENDENCY_PREFLIGHT_BLOCKED",
            "failure_message": "approved dependency is incompatible",
        }
    }
    group_key = TransformerOrchestrator._deterministic_replan_group_key(evidence)
    intelligence = type(
        "Intelligence",
        (),
        {"root_causes": {group_key: {"taxonomy": "dependency", "root_cause_code": "DEPENDENCY_PREFLIGHT_BLOCKED"}}},
    )()
    assert TransformerOrchestrator._has_deterministic_replan_intelligence(
        _Session(intelligence), _Continuation(), evidence
    ) is True

    intelligence.root_causes[group_key]["taxonomy"] = "command"
    assert TransformerOrchestrator._has_deterministic_replan_intelligence(
        _Session(intelligence), _Continuation(), evidence
    ) is False
