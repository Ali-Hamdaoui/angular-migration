"""Partial migration delivery API (V2 F26)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.partial_delivery_contracts import (
    PartialDeliveryDecisionDto,
    PartialDeliveryListDto,
    PartialDeliveryRecordDto,
    PartialDeliveryRequest,
    PartialDeliveryResumeDto,
)
from app.services.partial_delivery_service import PartialDeliveryError, PartialDeliveryService

router = APIRouter(tags=["partial-delivery"])


def get_delivery_service() -> PartialDeliveryService:
    return PartialDeliveryService()


def _raise(error: PartialDeliveryError) -> None:
    raise HTTPException(status_code=404 if error.code in {"RUN_NOT_FOUND", "NO_SEALED_STAGE", "NO_PARTIAL_DELIVERY"} else 422,
                        detail={"error_code": error.code, "message": error.message})


def _decision_dto(d) -> PartialDeliveryDecisionDto:
    return PartialDeliveryDecisionDto(run_id=d.run_id, delivered_at_stage=d.delivered_at_stage,
                                      delivered_fingerprint=d.delivered_fingerprint, validated=d.validated,
                                      remaining_stages=list(d.remaining_stages), resumable=d.resumable,
                                      checksum=d.checksum)


def _record_dto(row) -> PartialDeliveryRecordDto:
    return PartialDeliveryRecordDto(id=row.id, run_id=row.run_id, delivered_at_stage=row.delivered_at_stage,
                                    delivered_fingerprint=row.delivered_fingerprint, validated=row.validated,
                                    remaining_stages=row.remaining_stages, resumable=row.resumable,
                                    blockers=row.blockers, checksum=row.checksum, created_at=row.created_at)


@router.post("/runs/{run_id}/partial-delivery", response_model=PartialDeliveryDecisionDto)
def deliver_partial(
    run_id: str,
    request: PartialDeliveryRequest,
    service: PartialDeliveryService = Depends(get_delivery_service),
) -> PartialDeliveryDecisionDto:
    try:
        decision = service.deliver_partial(run_id, Path(request.workspace_path))
    except PartialDeliveryError as error:
        _raise(error)
    return _decision_dto(decision)


@router.post("/runs/{run_id}/partial-delivery/resume", response_model=PartialDeliveryResumeDto)
def resume_partial(
    run_id: str,
    service: PartialDeliveryService = Depends(get_delivery_service),
) -> PartialDeliveryResumeDto:
    try:
        resume = service.resume_partial(run_id)
    except PartialDeliveryError as error:
        _raise(error)
    return PartialDeliveryResumeDto(**resume)


@router.get("/runs/{run_id}/partial-deliveries", response_model=PartialDeliveryListDto)
def list_partial_deliveries(
    run_id: str,
    service: PartialDeliveryService = Depends(get_delivery_service),
) -> PartialDeliveryListDto:
    return PartialDeliveryListDto(deliveries=[_record_dto(row) for row in service.list_partial_deliveries(run_id)])
