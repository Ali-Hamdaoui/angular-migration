"""Thin mock API service for Sprint 0 route shells."""

from datetime import UTC, datetime

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
from app.preflight import PreflightService
from app.services.mock_migration_service import get_mock_migration_run

VALID_PREFLIGHT_CHECKSUM = "mock-preflight-checksum-angular-18-to-21"
EXPIRED_PREFLIGHT_CHECKSUM = "expired-preflight-checksum"


class AutoApprovalNotAllowedError(ValueError):
    """Production workflow never advances gates through automatic approval."""

    error_code = "AUTO_APPROVAL_NOT_ALLOWED"
    message = "Production auto-approval is disabled; submit an explicit human decision."


class PreflightChecksumError(ValueError):
    """Raised when mock run creation is not bound to a current preflight."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class MockMigrationApiService:
    """Service boundary for Sprint 0 mock migration API shells."""

    def __init__(self, preflight_service: PreflightService | None = None) -> None:
        self._preflight_service = preflight_service or PreflightService()

    def validate_preflight(self, request: PreflightRequestDto) -> PreflightResultDto:
        return self._preflight_service.validate(request)

    def create_mock_run(self, request: CreateMockMigrationRequestDto) -> MigrationRunDto:
        if request.preflight_checksum == EXPIRED_PREFLIGHT_CHECKSUM:
            raise PreflightChecksumError(
                "preflight_checksum_expired",
                "Preflight checksum is expired; run preflight again.",
            )
        if not self._preflight_service.is_current_and_runnable(request.preflight_checksum):
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
        if request.auto_approval_enabled:
            raise AutoApprovalNotAllowedError()
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
