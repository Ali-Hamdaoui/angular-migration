"""API contracts for failure intelligence (V2 F19)."""

from datetime import datetime
from typing import Any, Literal

from app.domain.contracts import ContractModel


class FailureGroupDto(ContractModel):
    group_key: str
    taxonomy: Literal["environment", "command", "dependency", "workflow", "state", "transport", "llm", "policy", "unknown"]
    fault_codes: list[str]
    member_count: int
    first_seen: datetime
    last_seen: datetime
    signature: str = ""
    checksum: str


class FailureRootCauseDto(ContractModel):
    group_key: str
    root_cause_code: str
    taxonomy: str
    explanation: str = ""
    confidence: Literal["high", "medium", "low"]
    contributing_codes: list[str]


class FailureDependencyEdgeDto(ContractModel):
    depends_on: str
    dependent: str
    reason: str = ""


class FailureDependencyGraphDto(ContractModel):
    nodes: list[FailureGroupDto]
    edges: list[FailureDependencyEdgeDto]
    checksum: str


class FailureIntelligenceDto(ContractModel):
    groups: list[FailureGroupDto]
    root_causes: dict[str, FailureRootCauseDto]
    graph: FailureDependencyGraphDto


class FailureIntelligenceRecordDto(ContractModel):
    id: str
    run_id: str
    groups: list[dict[str, Any]]
    root_causes: dict[str, Any]
    graph: dict[str, Any]
    checksum: str
    created_at: datetime
