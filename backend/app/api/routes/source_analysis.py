"""Deterministic source-analysis API."""

from fastapi import APIRouter, Depends, HTTPException
from app.core.config import get_settings
from app.domain.source_analysis import SourceAnalysisRequest, SourceAnalysisResult
from app.services.source_analysis_application_service import SourceAnalysisApplicationService

router = APIRouter(prefix="/sources", tags=["sources"])


def get_source_analysis_service() -> SourceAnalysisApplicationService:
    return SourceAnalysisApplicationService(get_settings())


@router.post("/analyze", response_model=SourceAnalysisResult)
def analyze_source(request: SourceAnalysisRequest, service: SourceAnalysisApplicationService = Depends(get_source_analysis_service)) -> SourceAnalysisResult:
    return service.analyze(request)


@router.get("/analyses/{analysis_id}", response_model=SourceAnalysisResult)
def get_source_analysis(analysis_id: str, service: SourceAnalysisApplicationService = Depends(get_source_analysis_service)) -> SourceAnalysisResult:
    result = service.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Source analysis not found")
    return result