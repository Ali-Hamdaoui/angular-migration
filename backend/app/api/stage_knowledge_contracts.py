"""API contracts for Angular stage knowledge (V2 F17)."""

from datetime import datetime
from typing import Any

from app.domain.contracts import ContractModel


class StageKnowledgeEntryDto(ContractModel):
    source_major: int
    target_major: int
    expected_transforms: list[str]
    validation_expectations: list[str]
    expected_dependency_changes: list[dict[str, str]]
    known_risks: list[str]
    version: int
    notes: str = ""


class StageKnowledgeEntryRecordDto(ContractModel):
    id: str
    source_major: int
    target_major: int
    expected_transforms: list[str]
    validation_expectations: list[str]
    expected_dependency_changes: list[dict[str, Any]]
    known_risks: list[str]
    version: int
    created_by: str | None = None
    change_reason: str | None = None
    notes: str | None = None
    created_at: datetime


class StageKnowledgeListDto(ContractModel):
    entries: list[StageKnowledgeEntryDto]


class StageKnowledgeRecordListDto(ContractModel):
    entries: list[StageKnowledgeEntryRecordDto]


class PersistKnowledgeRequest(ContractModel):
    actor: str | None = None
    reason: str | None = None
