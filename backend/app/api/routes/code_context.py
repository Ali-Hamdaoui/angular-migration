"""Code context intelligence API (V2 F20)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.code_context_contracts import (
    CodeContextBundleDto,
    CodeContextUnitDto,
    RetrieveContextRequest,
)
from app.services.code_context_service import CodeContextError, CodeContextService

router = APIRouter(tags=["code-context"])


def get_context_service() -> CodeContextService:
    return CodeContextService()


def _raise(error: CodeContextError) -> None:
    raise HTTPException(status_code=422, detail={"error_code": error.code, "message": error.message})


def _unit_dto(u) -> CodeContextUnitDto:
    return CodeContextUnitDto(path=u["path"] if isinstance(u, dict) else u.path,
                              kind=u["kind"] if isinstance(u, dict) else u.kind,
                              symbol=u.get("symbol", "") if isinstance(u, dict) else u.symbol,
                              excerpt=u["excerpt"] if isinstance(u, dict) else u.excerpt,
                              start_line=u["start_line"] if isinstance(u, dict) else u.start_line,
                              end_line=u["end_line"] if isinstance(u, dict) else u.end_line,
                              token_count=u["token_count"] if isinstance(u, dict) else u.token_count)


def _bundle_dto(bundle) -> CodeContextBundleDto:
    return CodeContextBundleDto(units=[_unit_dto(u) for u in bundle.units],
                                total_tokens=bundle.total_tokens, budget=bundle.budget,
                                truncated=bundle.truncated, checksum=bundle.checksum)


@router.post("/context/retrieve", response_model=CodeContextBundleDto)
def retrieve_context(
    request: RetrieveContextRequest,
    service: CodeContextService = Depends(get_context_service),
) -> CodeContextBundleDto:
    try:
        bundle = service.retrieve_context(
            Path(request.workspace_path),
            request.symbols,
            request.template_selectors,
            budget=request.budget,
        )
    except CodeContextError as error:
        _raise(error)
    return _bundle_dto(bundle)
