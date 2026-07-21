from __future__ import annotations

import pytest

from app.domain.planning_review import G06Gate
from app.domain.planning import PlanGenerationRequest
from app.domain.planning_review import PlanRevisionChanges, PlanRevisionRequest
from app.services.planning_review_application_service import PlanRevisionService, PlanningReviewApplicationError


def _generation():
    from app.services.planning_application_service import PlanningApplicationService

    return PlanningApplicationService().generate(PlanGenerationRequest(
        run_id="run-1", expected_state_version=4, idempotency_key="plan-1", actor="operator",
        source_exact="18.2.13", source_family="angular-18.x", target_family="angular-21.x",
        catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
        execution_profile_id="profile-node22-npm10", builder="@angular-devkit/build-angular:application",
        target_cli_exact="19.2.0", stage_route=(
            ("angular-18.x", "angular-19.x", "stage-18-to-19", "19.2.0"),
            ("angular-19.x", "angular-20.x", "stage-19-to-20", "20.0.0"),
            ("angular-20.x", "angular-21.x", "stage-20-to-21", "21.0.0"),
        ),
    ))


def _revision_request(result, **changes):
    return PlanRevisionRequest(
        run_id="run-1", expected_state_version=4, idempotency_key="revision-1", actor="operator",
        plan=result.plan.model_dump(mode="json"), stage_plan=result.first_stage_plan.model_dump(mode="json"),
        changes=PlanRevisionChanges(**changes), artifact_set_checksum="sha256:" + "2" * 64,
    )


def test_verification_rejects_tampered_plan_binding_before_revision():
    generated = _generation()
    service = PlanRevisionService()
    request = _revision_request(generated, catalogue_version="catalog-v2").model_copy(
        update={"plan": {**generated.plan.model_dump(mode="json"), "checksum": "sha256:" + "f" * 64}}
    )

    with pytest.raises(PlanningReviewApplicationError) as error:
        service.revise(request)

    assert error.value.code == "PLAN_BINDING_MISMATCH"


def test_verification_rejects_unapproved_builder_revision():
    generated = _generation()
    with pytest.raises(PlanningReviewApplicationError) as error:
        PlanRevisionService().revise(_revision_request(generated, builder="custom:unsafe-builder"))

    assert error.value.code == "UNSUPPORTED_BUILD_SYSTEM"


def test_verification_blocks_stage_start_for_stale_approved_g06_binding():
    generated = _generation()
    checksum = "sha256:" + "2" * 64
    gate = G06Gate(
        run_id="run-1",
        gate_version="g06-v1",
        status="approved",
        artifact_set_checksum=checksum,
        plan_checksum=generated.plan.checksum,
        stage_plan_checksum=generated.first_stage_plan.checksum,
        state_version=5,
    )

    with pytest.raises(PlanningReviewApplicationError) as error:
        PlanRevisionService().require_approved_g06(
            gate,
            state_version=6,
            artifact_set_checksum=checksum,
            plan_checksum=generated.plan.checksum,
            stage_plan_checksum=generated.first_stage_plan.checksum,
            workspace_fingerprint=None,
        )

    assert error.value.code == "G06_STALE"
