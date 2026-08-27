from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.proven_failure import FailureBundle, FailureCategory, FailureOwner, MigrationFailureEnvelope
from app.services.failure_classifier import FailureClassifier, RepairDecision
from app.services.proven_stage_execution_service import (
    ProvenStageExecutionError,
    _require_target_cohort,
)
from app.services.proven_stage_tooling_policy import ProvenStageToolingPolicy
from app.services.stage_recovery_policy_service import (
    RecoveryAction,
    RecoveryFailureClass,
    StageRecoveryPolicyContext,
    StageRecoveryPolicyService,
    UnknownFailureRecommendation,
)


def _context(**changes):
    values = {
        "run_id": "run-a",
        "stage_id": "generated-stage-a",
        "stage_status": "blocked",
        "failure_code": "FAILURE",
        "failure_message": "message-a",
        "failure_class": RecoveryFailureClass.DEPENDENCY_INCOMPATIBLE,
        "evidence_refs": ("evidence-a",),
        "checkpoint_present": True,
        "checkpoint_safe": True,
        "workspace_authority_valid": True,
        "active_command": False,
        "active_gate": None,
        "gate_binding_stale": False,
        "stage_output_invalid": False,
        "introduced_by_migration": False,
        "command_id": "npm-install",
        "reconstruction_required": False,
        "retry_budget_exhausted": False,
    }
    values.update(changes)
    return StageRecoveryPolicyContext(**values)


def test_stage_ids_do_not_change_policy_decision():
    policy = StageRecoveryPolicyService()

    first = policy.decide(_context(stage_id="angular-15-to-16--one"))
    second = policy.decide(_context(stage_id="future-generated-stage--two"))

    assert first == second


def test_error_messages_do_not_change_policy_decision():
    policy = StageRecoveryPolicyService()

    first = policy.decide(_context(failure_message="first text"))
    second = policy.decide(_context(failure_message="different text"))

    assert first == second


def test_unknown_failure_escalates_without_automatic_mutation():
    decision = StageRecoveryPolicyService().decide(
        _context(failure_class=RecoveryFailureClass.UNKNOWN_FAILURE)
    )

    assert decision.allowed is False
    assert decision.action is RecoveryAction.ESCALATE_UNKNOWN


def test_unknown_output_failure_is_not_promoted_to_source_regression():
    decision = StageRecoveryPolicyService().decide(
        _context(
            failure_class=RecoveryFailureClass.UNKNOWN_FAILURE,
            stage_output_invalid=True,
            introduced_by_migration=True,
        )
    )

    assert decision.action is RecoveryAction.ESCALATE_UNKNOWN


def test_supported_llm_analysis_is_revalidated_by_deterministic_policy():
    recommendation = UnknownFailureRecommendation(
        failure_class="ENVIRONMENT_TRANSIENT",
        probable_root_cause="the registry was temporarily unavailable",
        proposed_owner="environment",
        recommended_action="RETRY_COMMAND",
        evidence_used=("evidence-a",),
        confidence=0.8,
    )

    decision = StageRecoveryPolicyService().decide_llm_recommendation(
        _context(failure_class=RecoveryFailureClass.UNKNOWN_FAILURE),
        recommendation,
    )

    assert decision.allowed is True
    assert decision.action is RecoveryAction.RETRY_COMMAND


def test_unsupported_llm_analysis_stays_escalated():
    recommendation = UnknownFailureRecommendation(
        failure_class="future-class",
        probable_root_cause="not enough evidence",
        proposed_owner="unknown",
        recommended_action="MUTATE_WORKSPACE",
        confidence=0.1,
    )

    decision = StageRecoveryPolicyService().decide_llm_recommendation(
        _context(failure_class=RecoveryFailureClass.UNKNOWN_FAILURE),
        recommendation,
    )

    assert decision.allowed is False
    assert decision.action is RecoveryAction.ESCALATE_UNKNOWN


def _failure_bundle(category, owner, *, repair_allowed=True):
    envelope = MigrationFailureEnvelope.create(
        category=category,
        phase="validation",
        code="UNCLASSIFIED_FAILURE",
        message="bounded failure evidence",
        recoverable=True,
        repair_allowed=repair_allowed,
        owner=owner,
    )
    return envelope, FailureBundle.create(envelope=envelope)


def test_llm_routing_allows_unknown_and_source_but_not_operational_repairs():
    calls = []
    classifier = FailureClassifier(
        llm_proposer=lambda bundle: calls.append(bundle.envelope.category) or {"proposal": "source-fix"}
    )

    source_envelope, source_bundle = _failure_bundle(
        FailureCategory.BUILD,
        FailureOwner.SOURCE_TRANSFORMATION,
    )
    unknown_envelope, unknown_bundle = _failure_bundle(
        FailureCategory.UNKNOWN,
        FailureOwner.HUMAN,
        repair_allowed=False,
    )
    environment_envelope, environment_bundle = _failure_bundle(
        FailureCategory.ENVIRONMENT,
        FailureOwner.PLATFORM_RECOVERY,
        repair_allowed=False,
    )

    assert classifier.classify(envelope=source_envelope, bundle=source_bundle).decision is RepairDecision.LLM_PROPOSER
    assert classifier.classify(envelope=unknown_envelope, bundle=unknown_bundle).decision is RepairDecision.LLM_PROPOSER
    assert classifier.classify(envelope=environment_envelope, bundle=environment_bundle).decision is RepairDecision.ESCALATE
    assert calls == [FailureCategory.BUILD, FailureCategory.UNKNOWN]


def test_dependency_failure_uses_generic_repair_action():
    decision = StageRecoveryPolicyService().decide(
        _context(
            failure_class=RecoveryFailureClass.DEPENDENCY_INCOMPATIBLE,
            failure_code="PEER_CONFLICT",
            failure_message="package-x conflicts with package-y",
        )
    )

    assert decision.allowed is True
    assert decision.action is RecoveryAction.REQUEST_REPAIR


def test_transient_environment_failure_retries_command():
    decision = StageRecoveryPolicyService().decide(
        _context(
            failure_class=RecoveryFailureClass.ENVIRONMENT_TRANSIENT,
            failure_code="NETWORK_TIMEOUT",
        )
    )

    assert decision.allowed is True
    assert decision.action is RecoveryAction.RETRY_COMMAND


def test_exhausted_transient_retry_budget_reexecutes_from_g07():
    decision = StageRecoveryPolicyService().decide(
        _context(
            failure_class=RecoveryFailureClass.ENVIRONMENT_TRANSIENT,
            retry_budget_exhausted=True,
        )
    )

    assert decision.allowed is True
    assert decision.action is RecoveryAction.REEXECUTE_FROM_G07


def test_stale_gate_is_recreated_without_stage_reexecution():
    decision = StageRecoveryPolicyService().decide(
        _context(
            failure_class=RecoveryFailureClass.STALE_GATE_BINDING,
            active_gate="G12",
            gate_binding_stale=True,
        )
    )

    assert decision.allowed is True
    assert decision.action is RecoveryAction.RECREATE_GATE


@pytest.mark.parametrize(
    "changes",
    [
        {"checkpoint_present": False},
        {"checkpoint_safe": False},
        {"workspace_authority_valid": False},
        {"active_command": True},
    ],
)
def test_unsafe_recovery_is_denied(changes):
    decision = StageRecoveryPolicyService().decide(_context(**changes))

    assert decision.allowed is False
    assert decision.action is RecoveryAction.DENY


def test_tooling_policy_resolves_families_without_exact_angular_versions():
    policy = ProvenStageToolingPolicy()

    current = policy.resolve("angular-15.x", "angular-16.x")
    future = policy.resolve("angular-16.x", "angular-17.x")

    assert current["karma"] == "~6.4.4"
    assert future["karma"] == "~6.4.4"


def test_future_stage_id_has_no_recovery_special_case():
    decision = StageRecoveryPolicyService().decide(
        _context(stage_id="angular-16-to-17--generated", failure_class=RecoveryFailureClass.COMMAND_INTERRUPTED)
    )

    assert decision.allowed is True
    assert decision.action is RecoveryAction.RETRY_COMMAND


def test_reconstruction_required_command_reexecutes_from_g07():
    decision = StageRecoveryPolicyService().decide(
        _context(
            failure_class=RecoveryFailureClass.COMMAND_INTERRUPTED,
            reconstruction_required=True,
        )
    )

    assert decision.allowed is True
    assert decision.action is RecoveryAction.REEXECUTE_FROM_G07


def test_continuation_dispatches_reexecution_to_stage_recovery_service(monkeypatch):
    from app.services import stage_recovery_service
    from app.services.transformation_continuation_service import TransformationContinuationService

    context = _context(
        failure_class=RecoveryFailureClass.SOURCE_REGRESSION,
        stage_output_invalid=True,
        introduced_by_migration=True,
    )
    calls = {}

    class Recovery:
        def reexecute_from_g07_in_session(self, session, continuation, **kwargs):
            calls["reexecute"] = kwargs
            return "rebuilt"

    service = TransformationContinuationService()
    service._recovery_policy_context = lambda session, continuation: context
    monkeypatch.setattr(stage_recovery_service, "StageRecoveryService", Recovery)

    result = service.reexecute_blocked_stage_from_g07(
        object(),
        SimpleNamespace(),
        expected_state_version=4,
        idempotency_key="recovery-1",
    )

    assert result == "rebuilt"
    assert calls["reexecute"]["expected_state_version"] == 4


def test_continuation_dispatches_stale_gate_to_gate_recreation(monkeypatch):
    from app.services import stage_recovery_service
    from app.services.transformation_continuation_service import TransformationContinuationService

    context = _context(
        stage_status="waiting_gate",
        failure_class=RecoveryFailureClass.STALE_GATE_BINDING,
        active_gate="G12",
        gate_binding_stale=True,
    )
    calls = {}

    class Recovery:
        def recreate_gate_in_session(self, session, continuation, **kwargs):
            calls["gate"] = kwargs

    service = TransformationContinuationService()
    service._recovery_policy_context = lambda session, continuation: context
    monkeypatch.setattr(stage_recovery_service, "StageRecoveryService", Recovery)

    result = service.reexecute_blocked_stage_from_g07(
        object(),
        SimpleNamespace(),
        expected_state_version=7,
        idempotency_key="gate-1",
    )

    assert result is None
    assert calls["gate"] == {
        "gate_id": "G12",
        "expected_state_version": 7,
        "idempotency_key": "gate-1",
    }


def test_continuation_has_no_incident_identity_recovery_checks():
    source = Path(
        "backend/app/services/transformation_continuation_service.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "angular-15-to-16--181a457f1430ae3b",
        "karma@5.1.1",
        "build-angular@16.2.16",
        "cannot find module 'source-map'",
        "__webpack_require__(...).context is not a function",
        "single package must be specified",
    ):
        assert forbidden not in source


def test_missing_target_cohort_is_structured_and_fails_closed():
    with pytest.raises(ProvenStageExecutionError) as raised:
        _require_target_cohort(
            {"@angular/core": "target"},
            source_family="angular-15.x",
            target_family="angular-16.x",
        )

    assert raised.value.code == "PROVEN_TARGET_COHORT_INCOMPLETE"
    assert raised.value.details["missing_packages"]
    assert "typescript" in raised.value.details["missing_packages"]
