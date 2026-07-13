from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.contracts import MigrationRunDto
from app.main import app


def test_contracts_reject_unknown_enum_values() -> None:
    with pytest.raises(ValidationError):
        MigrationRunDto.model_validate(
            {
                "run_id": "run-001",
                "status": "UNKNOWN_STATE",
                "source_angular_version": "18.x",
                "target_angular_version": "21.x",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "stages": [
                    {
                        "stage_id": "stage-001",
                        "run_id": "run-001",
                        "stage_order": 1,
                        "source_angular_version": "18.x",
                        "target_angular_version": "19.x",
                        "status": "PENDING",
                        "created_at": datetime.now(UTC),
                    }
                ],
            }
        )

def test_terminal_runs_reject_active_stage_statuses() -> None:
    with pytest.raises(ValidationError):
        MigrationRunDto.model_validate(
            {
                "run_id": "run-001",
                "status": "COMPLETED",
                "source_angular_version": "18.x",
                "target_angular_version": "21.x",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "stages": [
                    {
                        "stage_id": "stage-001",
                        "run_id": "run-001",
                        "stage_order": 1,
                        "source_angular_version": "18.x",
                        "target_angular_version": "19.x",
                        "status": "RUNNING",
                        "created_at": datetime.now(UTC),
                    }
                ],
            }
        )

def test_openapi_publishes_every_sprint_zero_contract() -> None:
    schemas = app.openapi()["components"]["schemas"]
    expected = {
        "MigrationRunDto",
        "MigrationStageDto",
        "AgentExecutionDto",
        "ValidationGateDto",
        "ApprovalEventDto",
        "ArtifactRefDto",
        "CommandRequestDto",
        "CommandResultDto",
        "PatchLedgerEntryDto",
        "RepairAttemptDto",
        "WorkflowEventDto",
        "RunStatus",
        "RunPhase",
        "StageStatus",
        "StepStatus",
        "AgentStatus",
        "ValidationStatus",
        "ApprovalDecision",
        "RiskLevel",
        "ArtifactType",
        "CommandStatus",
    }

    assert expected.issubset(schemas)
    assert (
        app.openapi()["paths"]["/migrations/mock-state"]["get"]["responses"]["200"]
        ["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MigrationRunDto"
    )
