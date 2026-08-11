from app.api.stage_execution_contracts import StageStartResponse


def test_stage_start_response_exposes_first_governed_command_bindings():
    checksum = "sha256:" + "a" * 64

    response = StageStartResponse.model_validate(
        {
            "run_id": "run-1",
            "stage_id": "angular-20-to-21",
            "status": "STAGE_CREATED",
            "plan_checksum": checksum,
            "stage_plan_checksum": checksum,
            "artifact_set_checksum": checksum,
            "state_version": 2,
            "event_sequence": 3,
            "first_command_authorization_id": "authorization-1",
            "first_command_execution_id": "execution-1",
        }
    )

    assert response.first_command_authorization_id == "authorization-1"
    assert response.first_command_execution_id == "execution-1"
