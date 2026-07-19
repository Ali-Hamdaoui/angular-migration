from __future__ import annotations

import pytest

from app.domain.planning import PlanGenerationRequest
from app.services.planning_application_service import PlanningApplicationError, PlanningApplicationService


def request(**updates) -> PlanGenerationRequest:
    value = dict(
        run_id="run-1", expected_state_version=4, idempotency_key="plan-1", actor="operator",
        source_exact="18.2.13", source_family="angular-18.x", target_family="angular-21.x",
        catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
        execution_profile_id="profile-node22-npm10", builder="@angular-devkit/build-angular:application",
        stage_route=(("angular-18.x", "angular-19.x", "stage-18-to-19", "19.2.0"), ("angular-19.x", "angular-20.x", "stage-19-to-20", "20.0.0"), ("angular-20.x", "angular-21.x", "stage-20-to-21", "21.0.0")),
    )
    value.update(updates)
    return PlanGenerationRequest(**value)


def test_generates_immutable_plan_and_exact_first_stage_contract():
    result = PlanningApplicationService().generate(request())
    assert result.status == "generated"
    assert result.plan.route == ("stage-18-to-19", "stage-19-to-20", "stage-20-to-21")
    assert result.first_stage_plan.target_exact == "19.2.0"
    assert result.first_stage_plan.commands["angular_update"][0].shell is False
    assert result.first_stage_plan.forbidden_change_policy.actions
    assert result.plan.checksum.startswith("sha256:")
    assert result.first_stage_plan.checksum.startswith("sha256:")


def test_rejects_stale_state_and_does_not_generate():
    service = PlanningApplicationService(state_version_reader=lambda _run_id: 5)
    with pytest.raises(PlanningApplicationError, match="stale") as error:
        service.generate(request())
    assert error.value.code == "STALE_STATE_VERSION"


def test_idempotent_retry_replays_and_payload_mismatch_is_rejected():
    service = PlanningApplicationService()
    first = service.generate(request())
    replay = service.generate(request())
    assert replay.idempotent_replay is True
    assert replay.plan.checksum == first.plan.checksum
    with pytest.raises(PlanningApplicationError) as error:
        service.generate(request(source_exact="18.2.14"))
    assert error.value.code == "IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_rejects_prerequisite_checksum_mismatch():
    service = PlanningApplicationService(artifact_checksum_reader=lambda _artifact_id: "sha256:" + "2" * 64)
    with pytest.raises(PlanningApplicationError) as error:
        service.generate(request(prerequisite_artifacts=({"artifact_id": "artifact-analysis", "checksum": "sha256:" + "3" * 64},)))
    assert error.value.code == "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"


def test_blocks_unsupported_builder_before_stage_plan_is_returned():
    with pytest.raises(PlanningApplicationError) as error:
        PlanningApplicationService().generate(request(builder="vendor:custom"))
    assert error.value.code == "UNSUPPORTED_BUILD_SYSTEM"


def test_rejects_shell_syntax_in_structured_command_reference():
    with pytest.raises(ValueError, match="shell syntax"):
        request(stage_route=(("angular-18.x", "angular-19.x", "stage-18-to-19;echo", "19.2.0"),))
