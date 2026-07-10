"""Migration read-model endpoints; no workflow logic lives in this router."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.domain.contracts import MigrationRunDto, PreflightRequestDto, PreflightResultDto
from app.services.mock_event_service import format_sse_event, generate_mock_events
from app.services.mock_migration_service import get_mock_migration_run
from app.services.preflight_service import run_preflight

router = APIRouter(prefix="/migrations", tags=["migrations"])


@router.get("/mock-state", response_model=MigrationRunDto, summary="Read mock migration state")
def read_mock_migration_state() -> MigrationRunDto:
    return get_mock_migration_run()


@router.post("/preflight", response_model=PreflightResultDto, summary="Validate setup inputs before mock run creation")
def validate_migration_preflight(request: PreflightRequestDto) -> PreflightResultDto:
    return run_preflight(request)


@router.get("/{run_id}/events", summary="Stream mock workflow events via Server-Sent Events")
async def stream_migration_events(run_id: str) -> StreamingResponse:
    async def event_stream():
        async for event in generate_mock_events(run_id):
            yield format_sse_event(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )