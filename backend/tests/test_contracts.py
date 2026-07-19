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
        "PhaseStatus",
        "ApprovalStatus",
        "RepairStatus",
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

def test_authoritative_dimensions_accept_documented_values() -> None:
    run = MigrationRunDto.model_validate(
        {
            "run_id": "run-authoritative",
            "status": "WAITING_ANALYSIS_APPROVAL",
            "phase_status": "waiting_approval",
            "approval_status": "pending",
            "repair_status": "not_required",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "stages": [
                {
                    "stage_id": "stage-001",
                    "run_id": "run-authoritative",
                    "stage_order": 1,
                    "status": "passed_with_manual_items",
                    "created_at": datetime.now(UTC),
                }
            ],
        }
    )
    assert run.approval_status.value == "pending"
    assert run.stages[0].status.value == "passed_with_manual_items"


# ------------------------------------------------------------------
# T02 / AMFA-283 — Acceptance harness contract tests
# ------------------------------------------------------------------


def test_acceptance_event_types_exist() -> None:
    """New WorkflowEventType entries exist in the Python enum."""
    from app.domain.contracts import WorkflowEventType

    expected_new = {
        "ACCEPTANCE_SUITE_STARTED",
        "ACCEPTANCE_SUITE_COMPLETED",
        "ACCEPTANCE_SUITE_FAILED",
        "FIXTURE_GENERATED",
        "FIXTURE_GENERATION_FAILED",
        "FIXTURE_EVALUATED",
        "FIXTURE_EVALUATION_FAILED",
        "FIXTURE_CANCELLED",
        "FIXTURE_RESTARTED",
        "OUTPUT_FINGERPRINT_CREATED",
        "REPAIR_LINEAGE_RECORDED",
    }
    enum_values = {e.value for e in WorkflowEventType}
    assert expected_new.issubset(enum_values), (
        f"Missing event types: {expected_new - enum_values}"
    )


def test_harness_run_status_dto_rejects_unknown_fields() -> None:
    """HarnessRunStatusDto rejects unknown fields (extra='forbid')."""
    from pydantic import ValidationError
    from app.domain.contracts import HarnessRunStatusDto

    with pytest.raises(ValidationError):
        HarnessRunStatusDto.model_validate(
            {
                "run_id": "harness-run-test",
                "overall_status": "COMPLETED",
                "unknown_field": "should_not_be_allowed",
            }
        )


def test_harness_run_status_dto_frozen() -> None:
    """HarnessRunStatusDto is frozen — mutation raises ValidationError."""
    from pydantic import ValidationError
    from app.domain.contracts import HarnessRunStatusDto

    dto = HarnessRunStatusDto(
        run_id="harness-run-test",
        overall_status="COMPLETED",
    )
    with pytest.raises(ValidationError):
        dto.overall_status = "FAILED"


def test_new_evidence_artifact_types_reflected() -> None:
    """ArtifactRefDto types are compatible with new evidence methods."""
    from app.domain.contracts import ArtifactRefDto, ArtifactType

    ref = ArtifactRefDto(
        artifact_id="artifact-test",
        run_id="harness-run-test",
        artifact_type=ArtifactType.JSON,
        relative_path="00_job_setup/cancellation_evidence_test.json",
        created_at=datetime.now(UTC),
        checksum="sha256:abcdef",
    )
    assert ref.artifact_type == ArtifactType.JSON
    assert ref.relative_path.endswith(".json")