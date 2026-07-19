"""API routes for the Acceptance Harness suite (Phase A, S4-F15-I01 / AMFA-282).

Endpoints:
- GET  /api/v1/operator/acceptance-suite/status          → HarnessStatusDto
- POST /api/v1/operator/acceptance-suite/fixtures         → HarnessResultDto (201)
- POST /api/v1/operator/acceptance-suite/fixtures/evaluate → HarnessResultDto
- GET  /api/v1/operator/acceptance-suite/runs             → runs list (T02)
- GET  /api/v1/operator/acceptance-suite/runs/{run_id}    → run details (T02)
- GET  /api/v1/operator/acceptance-suite/runs/{run_id}/evidence → evidence refs (T02)
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from functools import lru_cache
from sqlalchemy import select, func

from app.api.errors import error_response
from app.domain.contracts import (
    ArtifactRefDto,
    ArtifactType,
    HarnessEvaluateRequestDto,
    HarnessRequestDto,
    HarnessResultDto,
    HarnessRunStatusDto,
    HarnessStatusDto,
)
from app.repositories.models import ArtifactMetadataModel
from app.repositories.session import session_scope
from app.services.acceptance_harness_service import (
    AcceptanceHarnessService,
    StaleStateVersionError,
)

router = APIRouter(
    prefix="/operator/acceptance-suite",
    tags=["acceptance"],
)


# ------------------------------------------------------------------
# Dependency injection
# ------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_harness_service() -> AcceptanceHarnessService:
    """Return a shared AcceptanceHarnessService instance.

    For Phase A this creates a fresh instance with default settings.
    Production will use proper DI via FastAPI dependency overrides.
    """
    from app.core.config import get_settings

    settings = get_settings()
    return AcceptanceHarnessService(settings)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get(
    "/status",
    response_model=HarnessStatusDto,
    summary="Read the current acceptance harness status",
)
def get_status(
    service: AcceptanceHarnessService = Depends(get_harness_service),
) -> HarnessStatusDto:
    """Return the overall harness status (READY when idle)."""
    return service.get_status()


@router.post(
    "/fixtures",
    response_model=HarnessResultDto,
    status_code=201,
    summary="Generate a new acceptance fixture",
)
def create_fixture(
    request: HarnessRequestDto,
    req: Request,
    service: AcceptanceHarnessService = Depends(get_harness_service),
) -> HarnessResultDto | JSONResponse:
    """Generate a fixture workspace for the given fixture type.

    Returns the HarnessResultDto with fixture_id, fixture_root, and evidence refs.
    """
    try:
        return service.generate_fixture(request)
    except StaleStateVersionError as exc:
        return error_response(
            req,
            status_code=409,
            error_code="STALE_STATE_VERSION",
            message=str(exc),
        )
    except ValueError as exc:
        return error_response(
            req,
            status_code=422,
            error_code="UNKNOWN_FIXTURE_TYPE",
            message=str(exc),
        )


@router.post(
    "/fixtures/evaluate",
    response_model=HarnessResultDto,
    summary="Evaluate a previously generated fixture",
)
def evaluate_fixture(
    request: HarnessEvaluateRequestDto,
    req: Request,
    service: AcceptanceHarnessService = Depends(get_harness_service),
) -> HarnessResultDto | dict:
    """Evaluate a fixture by running ng build."""
    try:
        return service.evaluate_fixture(request.fixture_id)
    except ValueError as exc:
        return error_response(
            req,
            status_code=422,
            error_code="FIXTURE_EVALUATION_FAILED",
            message=str(exc),
        )


# ------------------------------------------------------------------
# Evidence retrieval endpoints (T02 / AMFA-283)
# ------------------------------------------------------------------


@router.get(
    "/runs",
    response_model=list[dict],
    summary="List all harness run IDs",
)
def list_harness_runs():
    """Query ArtifactMetadataModel for all harness run entries.

    Returns a list of unique run_ids with their latest evidence metadata.
    """
    with session_scope() as session:
        rows = (
            session.execute(
                select(
                    ArtifactMetadataModel.run_id,
                    func.count(ArtifactMetadataModel.id).label("artifact_count"),
                    func.max(ArtifactMetadataModel.created_at).label("latest_event"),
                )
                .where(ArtifactMetadataModel.run_id.like("harness-%"))
                .group_by(ArtifactMetadataModel.run_id)
                .order_by(func.max(ArtifactMetadataModel.created_at).desc())
            )
            .mappings()
            .all()
        )
    return [
        {
            "run_id": row["run_id"],
            "artifact_count": row["artifact_count"],
            "latest_event": (
                row["latest_event"].isoformat() if row["latest_event"] else None
            ),
        }
        for row in rows
    ]


@router.get(
    "/runs/{run_id}",
    response_model=HarnessRunStatusDto,
    summary="Get full details for a harness run",
)
def get_harness_run(run_id: str, req: Request):
    """Return full run details with all evidence refs.

    Returns 404 if the run_id is not found.
    """
    with session_scope() as session:
        artifacts = (
            session.execute(
                select(ArtifactMetadataModel)
                .where(ArtifactMetadataModel.run_id == run_id)
                .order_by(ArtifactMetadataModel.artifact_type, ArtifactMetadataModel.relative_path)
            )
            .scalars()
            .all()
        )

    if not artifacts:
        return error_response(
            req,
            status_code=404,
            error_code="RUN_NOT_FOUND",
            message=f"No artifacts found for run_id: {run_id}",
        )

    evidence_refs = [
        ArtifactRefDto(
            artifact_id=a.id,
            run_id=a.run_id,
            stage_id=a.stage_id,
            artifact_type=ArtifactType(a.artifact_type) if a.artifact_type in ArtifactType._value2member_map_ else ArtifactType.JSON,
            relative_path=a.relative_path,
            created_at=a.created_at,
            checksum=a.checksum,
        )
        for a in artifacts
    ]

    return HarnessRunStatusDto(
        run_id=run_id,
        overall_status="COMPLETED",
        fixture_count=len(evidence_refs),
        evidence_refs=evidence_refs,
    )


@router.get(
    "/runs/{run_id}/evidence",
    response_model=list[ArtifactRefDto],
    summary="Get all evidence artifacts for a harness run",
)
def get_harness_run_evidence(run_id: str, req: Request):
    """Return all evidence artifact refs for a given harness run.

    Returns 404 if the run_id is not found.
    """
    with session_scope() as session:
        artifacts = (
            session.execute(
                select(ArtifactMetadataModel)
                .where(ArtifactMetadataModel.run_id == run_id)
                .order_by(ArtifactMetadataModel.artifact_type, ArtifactMetadataModel.relative_path)
            )
            .scalars()
            .all()
        )

    if not artifacts:
        return error_response(
            req,
            status_code=404,
            error_code="RUN_NOT_FOUND",
            message=f"No artifacts found for run_id: {run_id}",
        )

    return [
        ArtifactRefDto(
            artifact_id=a.id,
            run_id=a.run_id,
            stage_id=a.stage_id,
            artifact_type=ArtifactType(a.artifact_type) if a.artifact_type in ArtifactType._value2member_map_ else ArtifactType.JSON,
            relative_path=a.relative_path,
            created_at=a.created_at,
            checksum=a.checksum,
        )
        for a in artifacts
    ]
