from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.planning_application_service import run_scoped_stage_id
from app.services.stage_plan_authority_service import StagePlanAuthorityService
from app.services.stage_recovery_policy_service import (
    RecoveryAction,
    RecoveryFailureClass,
    StageRecoveryPolicyContext,
    StageRecoveryPolicyService,
)


def _authority_inputs(stage_id: str):
    catalogue = CompatibilityCatalogueProvider().load()
    entry = catalogue.entry_for("angular-16.x", "angular-17.x")
    assert entry is not None
    return catalogue, entry, {
        "source_family": entry.source_family,
        "target_family": entry.target_family,
        "target_exact": entry.target_angular_exact,
        "target_cli_exact": entry.target_cli_exact,
        "target_cohort": entry.target_cohort(),
        "stage_id": stage_id,
    }


def test_run_scoped_stage_identity_is_idempotent_for_reused_route_data():
    run_id = "run-generic-reexecution"
    catalogue_stage_id = "stage-a-to-b"

    scoped = run_scoped_stage_id(run_id, catalogue_stage_id)

    assert run_scoped_stage_id(run_id, scoped) == scoped


def test_pre_execution_authority_refresh_is_independent_of_generated_ids():
    service = StagePlanAuthorityService()
    catalogue, entry, current = _authority_inputs("stage-generated-a")
    plan = {"catalogue_version": catalogue.version, "catalogue_checksum": catalogue.checksum}

    stale_a = dict(current, stage_id="stage-generated-a", target_exact="17.0.0", target_cli_exact="17.0.0")
    stale_a["target_cohort"] = {"@angular/core": "17.0.0"}
    stale_b = dict(stale_a, stage_id="stage-generated-b")

    first = service.compare(stale_a, plan)
    second = service.compare(stale_b, plan)

    assert first.stale is True
    assert second.stale is True
    assert first.reason_code == "STAGE_PLAN_AUTHORITY_STALE"
    assert second.reason_code == first.reason_code
    assert first.differences == second.differences
    assert first.authority.target_cohort["typescript"] == "5.4.5"


def test_authority_refresh_ignores_error_text_and_requires_complete_current_cohort():
    service = StagePlanAuthorityService()
    catalogue, entry, current = _authority_inputs("stage-with-arbitrary-error")
    plan = {"catalogue_version": catalogue.version, "catalogue_checksum": catalogue.checksum}

    result = service.compare(current, plan)
    assert result.stale is False
    assert result.reason_code is None
    assert result.authority.target_exact == entry.target_angular_exact
    assert set(result.authority.target_cohort) >= {"typescript", "rxjs", "zone.js"}


def test_stale_plan_policy_allows_only_safe_pre_execution_recovery():
    context = StageRecoveryPolicyContext(
        run_id="run-a",
        stage_id="stage-a",
        stage_status="waiting_gate",
        failure_class=RecoveryFailureClass.STAGE_PLAN_AUTHORITY_STALE,
        evidence_refs=("plan-a", "checkpoint-a"),
        checkpoint_present=True,
        checkpoint_safe=True,
        workspace_authority_valid=True,
        plan_authority_stale=True,
    )
    decision = StageRecoveryPolicyService().decide(context)
    assert decision.allowed is True
    assert decision.action is RecoveryAction.REEXECUTE_FROM_G07
    assert decision.reason_code == "STAGE_PLAN_AUTHORITY_REFRESH_ALLOWED"

    for unsafe in (
        dict(commands_executed=True),
        dict(checkpoint_present=False),
        dict(workspace_authority_valid=False),
        dict(active_command=True),
    ):
        denied = StageRecoveryPolicyService().decide(
            StageRecoveryPolicyContext(**{**context.__dict__, **unsafe})
        )
        assert denied.allowed is False


def test_unknown_failure_never_selects_automatic_plan_refresh():
    decision = StageRecoveryPolicyService().decide(
        StageRecoveryPolicyContext(
            stage_status="waiting_gate",
            failure_class=RecoveryFailureClass.UNKNOWN_FAILURE,
            checkpoint_present=True,
            checkpoint_safe=True,
            workspace_authority_valid=True,
            plan_authority_stale=True,
        )
    )
    assert decision.allowed is False
    assert decision.action is RecoveryAction.ESCALATE_UNKNOWN


def test_command_authority_mismatch_allows_only_pre_execution_refresh():
    context = StageRecoveryPolicyContext(
        stage_status="blocked",
        failure_class=RecoveryFailureClass.COMMAND_AUTHORITY_MISMATCH,
        checkpoint_present=True,
        checkpoint_safe=True,
        workspace_authority_valid=True,
        command_authority_mismatch=True,
    )
    decision = StageRecoveryPolicyService().decide(context)
    assert decision.allowed is True
    assert decision.action is RecoveryAction.REEXECUTE_FROM_G07
    assert decision.reason_code == "COMMAND_AUTHORITY_REFRESH_ALLOWED"

    for unsafe in (
        dict(commands_executed=True),
        dict(stage_output_invalid=True),
        dict(command_authority_mismatch=False),
    ):
        denied = StageRecoveryPolicyService().decide(
            StageRecoveryPolicyContext(**{**context.__dict__, **unsafe})
        )
        assert denied.allowed is False
