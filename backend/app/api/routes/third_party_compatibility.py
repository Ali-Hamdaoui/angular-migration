"""Third-party compatibility scanner API (V2 F15)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.third_party_compatibility_contracts import (
    CompatibilityReportDto,
    CompatibilityReportListDto,
    CompatibilityReportRecordDto,
    DependencyFindingDto,
    DependencyInventoryItemDto,
    ScanStageRequest,
)
from app.services.third_party_compatibility_service import (
    ThirdPartyCompatibilityError,
    ThirdPartyCompatibilityScanner,
)

router = APIRouter(tags=["third-party-compatibility"])


def get_scanner() -> ThirdPartyCompatibilityScanner:
    return ThirdPartyCompatibilityScanner()


def _raise(error: ThirdPartyCompatibilityError) -> None:
    raise HTTPException(status_code=404 if error.code in {"RUN_NOT_FOUND", "STAGE_NOT_FOUND"} else 422,
                        detail={"error_code": error.code, "message": error.message})


def _item_dto(item) -> DependencyInventoryItemDto:
    return DependencyInventoryItemDto(name=item.name, declared=item.declared, resolved=item.resolved, scope=item.scope)


def _finding_dto(finding) -> DependencyFindingDto:
    return DependencyFindingDto(name=finding.name, declared=finding.declared, resolved=finding.resolved, target_major=finding.target_major, status=finding.status, detail=finding.detail)


def _report_dto(report) -> CompatibilityReportDto:
    return CompatibilityReportDto(
        run_id=report.run_id, stage_id=report.stage_id,
        source_major=report.source_major, target_major=report.target_major,
        status=report.status, blockers=list(report.blockers),
        inventory=[_item_dto(i) for i in report.inventory],
        findings=[_finding_dto(f) for f in report.findings],
    )


def _record_dto(row) -> CompatibilityReportRecordDto:
    return CompatibilityReportRecordDto(
        id=row.id, run_id=row.run_id, stage_id=row.stage_id,
        source_major=row.source_major, target_major=row.target_major,
        status=row.status, blockers=row.blockers,
        inventory=row.inventory, findings=row.findings, created_at=row.created_at,
    )


@router.post("/runs/{run_id}/stages/{stage_id}/compatibility/scan", response_model=CompatibilityReportDto)
def scan_stage_dependencies(
    run_id: str,
    stage_id: str,
    request: ScanStageRequest,
    service: ThirdPartyCompatibilityScanner = Depends(get_scanner),
) -> CompatibilityReportDto:
    try:
        report = service.scan_stage(Path(request.workspace_path), run_id=run_id, stage_id=stage_id)
    except ThirdPartyCompatibilityError as error:
        _raise(error)
    return _report_dto(report)


@router.post("/runs/{run_id}/stages/{stage_id}/compatibility/reports", response_model=CompatibilityReportRecordDto)
def persist_stage_compatibility_report(
    run_id: str,
    stage_id: str,
    request: ScanStageRequest,
    service: ThirdPartyCompatibilityScanner = Depends(get_scanner),
) -> CompatibilityReportRecordDto:
    try:
        report = service.scan_stage(Path(request.workspace_path), run_id=run_id, stage_id=stage_id)
        row = service.persist(run_id, report)
    except ThirdPartyCompatibilityError as error:
        _raise(error)
    return _record_dto(row)


@router.get("/runs/{run_id}/stages/{stage_id}/compatibility/reports", response_model=CompatibilityReportListDto)
def list_stage_compatibility_reports(
    run_id: str,
    stage_id: str,
    service: ThirdPartyCompatibilityScanner = Depends(get_scanner),
) -> CompatibilityReportListDto:
    return CompatibilityReportListDto(reports=[_record_dto(row) for row in service.list_stage_reports(stage_id)])
