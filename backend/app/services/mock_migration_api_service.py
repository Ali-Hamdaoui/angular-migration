"""Thin mock API service for AMF-S0-02 route shells."""

from datetime import UTC, datetime, timedelta

from app.domain.contracts import (
    ApprovalDecision,
    ApprovalEventDto,
    ApprovalPolicyDto,
    ApprovalPolicyRequestDto,
    ApprovalRequestDto,
    AssistantMessageRequestDto,
    AssistantMessageResponseDto,
    CreateMockMigrationRequestDto,
    MigrationRunDto,
    OperationResultDto,
    PreflightRequestDto,
    PreflightResultDto,
)
from app.services.mock_migration_service import get_mock_migration_run

VALID_PREFLIGHT_CHECKSUM = "mock-preflight-checksum-angular-18-to-21"
EXPIRED_PREFLIGHT_CHECKSUM = "expired-preflight-checksum"


class PreflightChecksumError(ValueError):
    """Raised when mock run creation is not bound to a current preflight."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class MockMigrationApiService:
    """Service boundary for Sprint 0 mock migration API shells."""

    def validate_preflight(self, request: PreflightRequestDto) -> PreflightResultDto:
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        return PreflightResultDto(
            preflight_id="mock-preflight-angular-18-to-21",
            checksum=VALID_PREFLIGHT_CHECKSUM,
            expires_at=expires_at,
            source_path=request.source_path,
            target_output_path=request.target_output_path,
            status="valid",
            message="Mock preflight accepted for the controlled Sprint 0 flow.",
        )

    def create_mock_run(self, request: CreateMockMigrationRequestDto) -> MigrationRunDto:
        if request.preflight_checksum == EXPIRED_PREFLIGHT_CHECKSUM:
            raise PreflightChecksumError(
                "preflight_checksum_expired",
                "Preflight checksum is expired; run preflight again.",
            )
        if request.preflight_checksum != VALID_PREFLIGHT_CHECKSUM:
            raise PreflightChecksumError(
                "preflight_checksum_invalid",
                "Create mock migration requires a valid preflight checksum.",
            )
        return get_mock_migration_run()

    def get_state(self, run_id: str) -> MigrationRunDto:
        return get_mock_migration_run().model_copy(update={"run_id": run_id})

    def submit_approval(self, run_id: str, request: ApprovalRequestDto) -> ApprovalEventDto:
        now = datetime.now(UTC)
        return ApprovalEventDto(
            approval_id=f"approval-{request.gate_id}",
            run_id=run_id,
            stage_id=None,
            decision=request.decision,
            requested_at=now,
            decided_at=now if request.decision != ApprovalDecision.PENDING else None,
            actor=request.actor,
            rationale=request.rationale,
        )

    def update_approval_policy(self, run_id: str, request: ApprovalPolicyRequestDto) -> ApprovalPolicyDto:
        return ApprovalPolicyDto(
            run_id=run_id,
            auto_approval_enabled=request.auto_approval_enabled,
            reevaluated_gate_id="approval-plan" if request.auto_approval_enabled else None,
            status="reevaluated",
        )

    def cancel_run(self, run_id: str) -> OperationResultDto:
        return OperationResultDto(
            run_id=run_id,
            operation="cancel",
            status="accepted",
            message="Mock cancellation request recorded idempotently.",
        )

    def resume_run(self, run_id: str) -> OperationResultDto:
        return OperationResultDto(
            run_id=run_id,
            operation="resume",
            status="accepted",
            message="Mock resume request recorded idempotently.",
        )

    def answer_assistant_message(self, request: AssistantMessageRequestDto) -> AssistantMessageResponseDto:
        return AssistantMessageResponseDto(
            run_id=request.run_id,
            response="Assistant route shell is available; Sprint 0 does not execute actions from chat.",
            status="mock_unavailable",
        )


_service = MockMigrationApiService()


def get_mock_migration_api_service() -> MockMigrationApiService:
    return _service
