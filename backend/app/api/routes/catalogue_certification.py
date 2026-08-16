"""Catalogue certification pipeline API (V2 F30)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.catalogue_certification_contracts import (
    CatalogueCertificationOutcomeDto,
    CatalogueCertificationRecordDto,
    CatalogueCertificationRunDto,
    CatalogueCertificationRunRequest,
)
from app.services.catalogue_certification_pipeline import (
    CatalogueCertificationError,
    CatalogueCertificationPipeline,
)

router = APIRouter(tags=["catalogue-certification"])


def get_pipeline() -> CatalogueCertificationPipeline:
    from app.core.config import get_settings

    roots = get_settings().allowed_source_roots
    if not roots:
        raise RuntimeError("ALLOWED_SOURCE_ROOTS must be configured for the catalogue certification endpoint")
    return CatalogueCertificationPipeline(allowed_roots=roots)


def _outcome_dto(o) -> CatalogueCertificationOutcomeDto:
    return CatalogueCertificationOutcomeDto(
        case_id=o.case_id, source_family=o.source_family, target_family=o.target_family,
        status=o.status.value, runtime_proof=[list(p) for p in o.runtime_proof],
        evidence=list(o.evidence), reason=o.reason, checksum=o.checksum,
    )


def _record_dto(r) -> CatalogueCertificationRecordDto:
    return CatalogueCertificationRecordDto(
        id=r.id, run_id=r.run_id, source_family=r.source_family, target_family=r.target_family,
        status=r.status, runtime_proof=list(r.runtime_proof), evidence=list(r.evidence),
        reason=r.reason, catalogue_version=r.catalogue_version, checksum=r.checksum, ran_at=r.ran_at,
    )


def _raise(error: CatalogueCertificationError) -> None:
    raise HTTPException(status_code=404 if error.code == "CERTIFICATION_NOT_FOUND" else 422,
                        detail={"error_code": error.code, "message": error.message})


@router.post("/catalogue-certification/run", response_model=CatalogueCertificationRunDto)
def run_pipeline(
    request: CatalogueCertificationRunRequest,
    pipeline: CatalogueCertificationPipeline = Depends(get_pipeline),
) -> CatalogueCertificationRunDto:
    try:
        run = pipeline.run(fixture_root=Path(request.fixture_root))
        pipeline.persist(run)
    except CatalogueCertificationError as error:
        _raise(error)
    return CatalogueCertificationRunDto(
        run_id=run.run_id, catalogue_version=run.catalogue_version,
        outcomes=[_outcome_dto(o) for o in run.outcomes],
        certified_count=run.certified_count, rejected_count=run.rejected_count,
        deterministic=run.deterministic, ran_at=run.ran_at, checksum=run.checksum,
    )


@router.get("/catalogue-certification", response_model=list[CatalogueCertificationRecordDto])
def list_certifications(
    source: str | None = Query(default=None),
    target: str | None = Query(default=None),
    pipeline: CatalogueCertificationPipeline = Depends(get_pipeline),
) -> list[CatalogueCertificationRecordDto]:
    return [_record_dto(r) for r in pipeline.list_certifications(source=source, target=target)]
