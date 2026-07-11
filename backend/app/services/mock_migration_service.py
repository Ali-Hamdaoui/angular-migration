"""Read-only backend-owned mock state for Sprint 0 UI integration."""

from datetime import UTC, datetime

from app.domain.contracts import (
    AgentExecutionDto,
    AgentStatus,
    ApprovalDecision,
    ApprovalEventDto,
    ArtifactRefDto,
    ArtifactType,
    AssuranceStatus,
    AssuranceStatusDto,
    CommandRequestDto,
    CommandResultDto,
    CommandStatus,
    DeliveryManifestDto,
    DeliveryStatus,
    MigrationRunDto,
    MigrationStageDto,
    PatchLedgerEntryDto,
    RepairAttemptDto,
    RiskLevel,
    RunStatus,
    StageStatus,
    ValidationGateDto,
    ValidationStatus,
    WorkflowEventDto,
)


def get_mock_migration_run() -> MigrationRunDto:
    """Build a fixed, backend-owned contract response; no workflow runs here."""
    now = datetime.now(UTC)
    run_id = "mock-run-angular-18-to-21"
    stage_id = "angular-18-to-19"
    report_artifact = ArtifactRefDto(
        artifact_id="artifact-mock-plan",
        run_id=run_id,
        stage_id=stage_id,
        artifact_type=ArtifactType.MARKDOWN,
        relative_path="03_planning/mock_migration_plan.md",
        created_at=now,
        checksum="mock-checksum-plan",
    )
    return MigrationRunDto(
        run_id=run_id,
        status=RunStatus.WAITING,
        source_angular_version="18.x",
        target_angular_version="21.x",
        created_at=now,
        updated_at=now,
        stages=[
            MigrationStageDto(stage_id=stage_id, run_id=run_id, stage_order=1, source_angular_version="18.x", target_angular_version="19.x", status=StageStatus.PENDING, created_at=now),
            MigrationStageDto(stage_id="angular-19-to-20", run_id=run_id, stage_order=2, source_angular_version="19.x", target_angular_version="20.x", status=StageStatus.PENDING, created_at=now),
            MigrationStageDto(stage_id="angular-20-to-21", run_id=run_id, stage_order=3, source_angular_version="20.x", target_angular_version="21.x", status=StageStatus.PENDING, created_at=now),
        ],
        agent_executions=[AgentExecutionDto(execution_id="agent-execution-planning", run_id=run_id, agent_name="Planning Agent", status=AgentStatus.COMPLETED, started_at=now, finished_at=now, summary="Mock plan prepared for approval.")],
        validation_gates=[ValidationGateDto(gate_id="gate-browser-smoke", run_id=run_id, stage_id=stage_id, name="browser_smoke", status=ValidationStatus.MANUAL_VALIDATION_REQUIRED, checked_at=now, details="Manual validation is required in Sprint 0.")],
        approval_events=[ApprovalEventDto(approval_id="approval-plan", run_id=run_id, decision=ApprovalDecision.PENDING, requested_at=now, rationale="Mock plan approval is pending.")],
        artifacts=[report_artifact],
        command_requests=[CommandRequestDto(command_id="command-stage-19", run_id=run_id, stage_id=stage_id, requester="Transformation Agent", executable="npx", arguments=["ng", "update", "@angular/core@19"], working_directory="sandbox://mock-run-angular-18-to-21", requested_at=now)],
        command_results=[CommandResultDto(command_id="command-stage-19", run_id=run_id, stage_id=stage_id, status=CommandStatus.PENDING, started_at=now)],
        patch_ledger=[PatchLedgerEntryDto(patch_id="patch-placeholder", run_id=run_id, stage_id=stage_id, affected_files=["src/app/app.config.ts"], change_summary="Mock placeholder only; no patch was applied.", risk_level=RiskLevel.LOW, created_at=now, validation_status=ValidationStatus.SKIPPED_NOT_APPLICABLE)],
        repair_attempts=[RepairAttemptDto(repair_attempt_id="repair-placeholder", run_id=run_id, stage_id=stage_id, attempt_number=1, status=AgentStatus.SKIPPED, risk_level=RiskLevel.LOW, created_at=now, diagnosis="No repair is required for mock state.")],
        assurance=AssuranceStatusDto(
            technical_upgrade_status=AssuranceStatus.NOT_EVALUATED,
            functional_parity_status=AssuranceStatus.MANUAL_REQUIRED,
            security_assurance_status=AssuranceStatus.NOT_EVALUATED,
            quality_assurance_status=AssuranceStatus.NOT_EVALUATED,
            delivery_readiness=AssuranceStatus.NOT_EVALUATED,
        ),
        delivery=DeliveryManifestDto(run_id=run_id, status=DeliveryStatus.NOT_PUBLISHED),
        workflow_events=[WorkflowEventDto(event_id="event-approval-required", run_id=run_id, event_type="approval_required", occurred_at=now, payload={"approval_id": "approval-plan", "status": RunStatus.WAITING.value})],
    )
