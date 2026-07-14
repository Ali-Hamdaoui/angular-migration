"""Migration route shells; no workflow logic lives in this router."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.errors import error_response
from app.domain.contracts import (
    ApprovalEventDto,
    ApprovalPolicyDto,
    ApprovalPolicyRequestDto,
    ApprovalRequestDto,
    AssistantMessageRequestDto,
    AssistantMessageResponseDto,
    CreateMockMigrationRequestDto,
    DiagnosticsSummaryDto,
    MigrationRunDto,
    OperationResultDto,
    PreflightRequestDto,
    PreflightResultDto,
)
from app.core.config import get_settings
from app.observability import build_diagnostics_summary
from app.services.mock_event_service import (
    ReplayUnavailableError,
    format_replay_unavailable,
    format_sse_event,
    generate_mock_events,
    get_retained_events,
)
from app.services.mock_migration_api_service import (
    MockMigrationApiService,
    AutoApprovalNotAllowedError,
    PreflightChecksumError,
    get_mock_migration_api_service,
)
from app.services.mock_migration_service import get_mock_migration_run

router = APIRouter(prefix="/migrations", tags=["migrations"])
assistant_router = APIRouter(prefix="/assistant", tags=["assistant"])


def get_service() -> MockMigrationApiService:
    return get_mock_migration_api_service()


@router.post("/preflight", response_model=PreflightResultDto, summary="Validate mock migration setup")
def validate_preflight(
    request: PreflightRequestDto,
    service: MockMigrationApiService = Depends(get_service),
) -> PreflightResultDto:
    return service.validate_preflight(request)


@router.post("/mock", response_model=MigrationRunDto, summary="Create a checksum-bound mock migration run")
def create_mock_migration(
    request: CreateMockMigrationRequestDto,
    http_request: Request,
    service: MockMigrationApiService = Depends(get_service),
):
    try:
        return service.create_mock_run(request)
    except PreflightChecksumError as exc:
        return error_response(
            http_request,
            status_code=400,
            error_code=exc.error_code,
            message=exc.message,
        )


@router.get("/mock-state", response_model=MigrationRunDto, summary="Read mock migration state")
def read_mock_migration_state() -> MigrationRunDto:
    return get_mock_migration_run()


@router.get("/{run_id}/state", response_model=MigrationRunDto, summary="Read migration state snapshot")
def read_migration_state(
    run_id: str,
    service: MockMigrationApiService = Depends(get_service),
) -> MigrationRunDto:
    return service.get_state(run_id)



@router.get("/{run_id}/diagnostics", response_model=DiagnosticsSummaryDto, summary="Read non-authoritative run diagnostics")
def read_migration_diagnostics(
    run_id: str,
    stage_id: str | None = None,
    service: MockMigrationApiService = Depends(get_service),
) -> DiagnosticsSummaryDto:
    run = service.get_state(run_id)
    return build_diagnostics_summary(run, events=get_retained_events(run_id), stage_id=stage_id)

@router.get("/{run_id}/events", summary="Stream mock workflow events via Server-Sent Events")
async def stream_migration_events(run_id: str, request: Request) -> StreamingResponse:
    raw_last_event_id = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    last_event_id = int(raw_last_event_id) if raw_last_event_id and raw_last_event_id.isdigit() else None
    settings = get_settings()

    async def event_stream():
        try:
            async for event in generate_mock_events(
                run_id,
                last_event_id=last_event_id,
                retention=settings.sse_replay_retention_events,
            ):
                yield event if isinstance(event, str) else format_sse_event(event)
        except ReplayUnavailableError:
            yield format_replay_unavailable(run_id, last_event_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/{run_id}/approvals", response_model=ApprovalEventDto, summary="Submit a mock approval decision")
def submit_approval(
    run_id: str,
    request: ApprovalRequestDto,
    service: MockMigrationApiService = Depends(get_service),
) -> ApprovalEventDto:
    return service.submit_approval(run_id, request)


@router.put("/{run_id}/approval-policy", response_model=ApprovalPolicyDto, summary="Update mock approval policy")
def update_approval_policy(
    run_id: str,
    request: ApprovalPolicyRequestDto,
    http_request: Request,
    service: MockMigrationApiService = Depends(get_service),
) -> ApprovalPolicyDto:
    try:
        return service.update_approval_policy(run_id, request)
    except AutoApprovalNotAllowedError as exc:
        return error_response(
            http_request,
            status_code=409,
            error_code=exc.error_code,
            message=exc.message,
        )


@router.post("/{run_id}/cancel", response_model=OperationResultDto, summary="Cancel a mock migration run")
def cancel_migration_run(
    run_id: str,
    service: MockMigrationApiService = Depends(get_service),
) -> OperationResultDto:
    return service.cancel_run(run_id)


@router.post("/{run_id}/resume", response_model=OperationResultDto, summary="Resume a mock migration run")
def resume_migration_run(
    run_id: str,
    service: MockMigrationApiService = Depends(get_service),
) -> OperationResultDto:
    return service.resume_run(run_id)


@assistant_router.post("/messages", response_model=AssistantMessageResponseDto, summary="Send a mock assistant message")
def send_assistant_message(
    request: AssistantMessageRequestDto,
    service: MockMigrationApiService = Depends(get_service),
) -> AssistantMessageResponseDto:
    return service.answer_assistant_message(request)
