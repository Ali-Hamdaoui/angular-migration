"""Angular stage knowledge API (V2 F17)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.stage_knowledge_contracts import (
    PersistKnowledgeRequest,
    StageKnowledgeEntryDto,
    StageKnowledgeEntryRecordDto,
    StageKnowledgeListDto,
    StageKnowledgeRecordListDto,
)
from app.services.stage_knowledge_service import StageKnowledgeError, StageKnowledgeRegistry

router = APIRouter(tags=["stage-knowledge"])


def get_knowledge_registry() -> StageKnowledgeRegistry:
    return StageKnowledgeRegistry()


def _raise(error: StageKnowledgeError) -> None:
    raise HTTPException(status_code=422, detail={"error_code": error.code, "message": error.message})


def _entry_dto(entry) -> StageKnowledgeEntryDto:
    return StageKnowledgeEntryDto(
        source_major=entry.source_major, target_major=entry.target_major,
        expected_transforms=list(entry.expected_transforms),
        validation_expectations=list(entry.validation_expectations),
        expected_dependency_changes=[dict(item) for item in entry.expected_dependency_changes],
        dependency_rules=[dict(item) for item in entry.dependency_rules],
        migration_actions=[dict(item) for item in entry.migration_actions],
        known_risks=list(entry.known_risks), version=entry.version, notes=entry.notes,
    )


def _record_dto(row) -> StageKnowledgeEntryRecordDto:
    return StageKnowledgeEntryRecordDto(
        id=row.id, source_major=row.source_major, target_major=row.target_major,
        expected_transforms=row.expected_transforms, validation_expectations=row.validation_expectations,
        expected_dependency_changes=row.expected_dependency_changes, known_risks=row.known_risks,
        dependency_rules=row.dependency_rules, migration_actions=row.migration_actions,
        version=row.version, created_by=row.created_by, change_reason=row.change_reason,
        notes=row.notes, created_at=row.created_at,
    )


@router.get("/stage-knowledge", response_model=StageKnowledgeListDto)
def list_stage_knowledge(
    registry: StageKnowledgeRegistry = Depends(get_knowledge_registry),
) -> StageKnowledgeListDto:
    return StageKnowledgeListDto(entries=[_entry_dto(entry) for entry in registry.entries()])


@router.get("/stage-knowledge/{source_major}/{target_major}", response_model=StageKnowledgeEntryDto)
def get_stage_knowledge(
    source_major: int,
    target_major: int,
    registry: StageKnowledgeRegistry = Depends(get_knowledge_registry),
) -> StageKnowledgeEntryDto:
    try:
        entry = registry.entry(source_major, target_major)
    except StageKnowledgeError as error:
        _raise(error)
    return _entry_dto(entry)


@router.post("/stage-knowledge/{source_major}/{target_major}/persist", response_model=StageKnowledgeEntryRecordDto)
def persist_stage_knowledge(
    source_major: int,
    target_major: int,
    request: PersistKnowledgeRequest,
    registry: StageKnowledgeRegistry = Depends(get_knowledge_registry),
) -> StageKnowledgeEntryRecordDto:
    try:
        entry = registry.entry(source_major, target_major)
        row = registry.persist(entry, actor=request.actor, reason=request.reason)
    except StageKnowledgeError as error:
        _raise(error)
    return _record_dto(row)


@router.get("/stage-knowledge/persisted", response_model=StageKnowledgeRecordListDto)
def list_persisted_stage_knowledge(
    registry: StageKnowledgeRegistry = Depends(get_knowledge_registry),
) -> StageKnowledgeRecordListDto:
    return StageKnowledgeRecordListDto(entries=[_record_dto(row) for row in registry.list_persisted()])
