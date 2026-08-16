"""V2 analyzer and planner API (F18)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.v2_planning_contracts import (
    AnalyzeRequest,
    V2AnalysisFindingDto,
    V2MigrationPlanDto,
    V2PlannedStageDto,
    V2PlanRecordDto,
)
from app.services.v2_planner_service import V2PlannerService, V2PlanningError

router = APIRouter(tags=["v2-planner"])


def get_planner_service() -> V2PlannerService:
    return V2PlannerService()


def _raise(error: V2PlanningError) -> None:
    raise HTTPException(status_code=404 if error.code == "RUN_NOT_FOUND" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _finding_dto(f) -> V2AnalysisFindingDto:
    return V2AnalysisFindingDto(finding_id=f["finding_id"] if isinstance(f, dict) else f.finding_id,
                                severity=f["severity"] if isinstance(f, dict) else f.severity,
                                message=f["message"] if isinstance(f, dict) else f.message)


def _stage_dto(s) -> V2PlannedStageDto:
    return V2PlannedStageDto(
        stage_order=s["stage_order"] if isinstance(s, dict) else s.stage_order,
        source_major=s["source_major"] if isinstance(s, dict) else s.source_major,
        target_major=s["target_major"] if isinstance(s, dict) else s.target_major,
        source_family=s["source_family"] if isinstance(s, dict) else s.source_family,
        target_family=s["target_family"] if isinstance(s, dict) else s.target_family,
        target_exact=s["target_exact"] if isinstance(s, dict) else s.target_exact,
        node_minimum=s.get("node_minimum") if isinstance(s, dict) else s.node_minimum,
        expected_transforms=s["expected_transforms"] if isinstance(s, dict) else list(s.expected_transforms),
        validation_expectations=s["validation_expectations"] if isinstance(s, dict) else list(s.validation_expectations),
    )


def _plan_dto(plan) -> V2MigrationPlanDto:
    return V2MigrationPlanDto(
        run_id=plan.run_id, source_major=plan.source_major, target_major=plan.target_major,
        catalogue_version=plan.catalogue_version,
        findings=[_finding_dto(f) for f in plan.findings],
        stages=[_stage_dto(s) for s in plan.stages],
        checksum=plan.checksum,
    )


def _record_dto(row) -> V2PlanRecordDto:
    return V2PlanRecordDto(
        id=row.id, run_id=row.run_id, source_major=row.source_major, target_major=row.target_major,
        catalogue_version=row.catalogue_version, findings=row.findings, stages=row.stages,
        checksum=row.checksum, created_at=row.created_at,
    )


@router.post("/runs/{run_id}/v2/analyze", response_model=list[V2AnalysisFindingDto])
def analyze_run(
    run_id: str,
    request: AnalyzeRequest,
    service: V2PlannerService = Depends(get_planner_service),
):
    try:
        findings = service.analyze(run_id, Path(request.source_root) if request.source_root else None)
    except V2PlanningError as error:
        _raise(error)
    return [_finding_dto(f) for f in findings]


@router.post("/runs/{run_id}/v2/plan", response_model=V2MigrationPlanDto)
def derive_plan(
    run_id: str,
    request: AnalyzeRequest,
    service: V2PlannerService = Depends(get_planner_service),
) -> V2MigrationPlanDto:
    try:
        plan = service.derive_plan(run_id, Path(request.source_root) if request.source_root else None)
    except V2PlanningError as error:
        _raise(error)
    return _plan_dto(plan)


@router.post("/runs/{run_id}/v2/plan/persist", response_model=V2PlanRecordDto)
def persist_plan(
    run_id: str,
    request: AnalyzeRequest,
    service: V2PlannerService = Depends(get_planner_service),
) -> V2PlanRecordDto:
    try:
        plan = service.derive_plan(run_id, Path(request.source_root) if request.source_root else None)
        row = service.persist(run_id, plan)
    except V2PlanningError as error:
        _raise(error)
    return _record_dto(row)


@router.post("/runs/{run_id}/v2/plan/validate", response_model=V2MigrationPlanDto)
def validate_run_plan(
    run_id: str,
    service: V2PlannerService = Depends(get_planner_service),
) -> V2MigrationPlanDto:
    try:
        plan = service.validate_plan(run_id)
    except V2PlanningError as error:
        _raise(error)
    return _plan_dto(plan)


@router.get("/runs/{run_id}/v2/plan", response_model=V2PlanRecordDto)
def get_run_plan(
    run_id: str,
    service: V2PlannerService = Depends(get_planner_service),
) -> V2PlanRecordDto:
    row = service.get_run_plan(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "PLAN_NOT_PERSISTED", "message": "No V2 plan persisted for run."})
    return _record_dto(row)
