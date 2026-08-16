"""Failure intelligence API (V2 F19)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.failure_intelligence_contracts import (
    FailureDependencyEdgeDto,
    FailureDependencyGraphDto,
    FailureGroupDto,
    FailureIntelligenceDto,
    FailureIntelligenceRecordDto,
    FailureRootCauseDto,
)
from app.services.failure_intelligence_service import FailureIntelligenceService

router = APIRouter(tags=["failure-intelligence"])


def get_intelligence_service() -> FailureIntelligenceService:
    return FailureIntelligenceService()


def _group_dto(g) -> FailureGroupDto:
    return FailureGroupDto(group_key=g.group_key, taxonomy=g.taxonomy, fault_codes=list(g.fault_codes),
                           member_count=g.member_count, first_seen=g.first_seen, last_seen=g.last_seen,
                           signature=g.signature, checksum=g.checksum)


def _root_dto(r) -> FailureRootCauseDto:
    return FailureRootCauseDto(group_key=r.group_key, root_cause_code=r.root_cause_code, taxonomy=r.taxonomy,
                               explanation=r.explanation, confidence=r.confidence,
                               contributing_codes=list(r.contributing_codes))


def _intelligence_dto(intelligence) -> FailureIntelligenceDto:
    groups = intelligence["groups"]
    roots = intelligence["root_causes"]
    graph = intelligence["graph"]
    return FailureIntelligenceDto(
        groups=[_group_dto(g) for g in groups],
        root_causes={k: _root_dto(v) for k, v in roots.items()},
        graph=FailureDependencyGraphDto(
            nodes=[_group_dto(n) for n in graph.nodes],
            edges=[FailureDependencyEdgeDto(depends_on=e.depends_on, dependent=e.dependent, reason=e.reason) for e in graph.edges],
            checksum=graph.checksum,
        ),
    )


def _record_dto(row) -> FailureIntelligenceRecordDto:
    return FailureIntelligenceRecordDto(id=row.id, run_id=row.run_id, groups=row.groups,
                                        root_causes=row.root_causes, graph=row.graph,
                                        checksum=row.checksum, created_at=row.created_at)


@router.post("/runs/{run_id}/failure-intelligence", response_model=FailureIntelligenceDto)
def build_failure_intelligence(
    run_id: str,
    service: FailureIntelligenceService = Depends(get_intelligence_service),
) -> FailureIntelligenceDto:
    return _intelligence_dto(service.intelligence_for_run(run_id))


@router.post("/runs/{run_id}/failure-intelligence/persist", response_model=FailureIntelligenceRecordDto)
def persist_failure_intelligence(
    run_id: str,
    service: FailureIntelligenceService = Depends(get_intelligence_service),
) -> FailureIntelligenceRecordDto:
    intelligence = service.intelligence_for_run(run_id)
    row = service.persist(run_id, intelligence)
    return _record_dto(row)


@router.get("/runs/{run_id}/failure-intelligence", response_model=FailureIntelligenceRecordDto)
def get_run_failure_intelligence(
    run_id: str,
    service: FailureIntelligenceService = Depends(get_intelligence_service),
) -> FailureIntelligenceRecordDto:
    row = service.get_run_intelligence(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "INTELLIGENCE_NOT_PERSISTED", "message": "No failure intelligence persisted for run."})
    return _record_dto(row)
