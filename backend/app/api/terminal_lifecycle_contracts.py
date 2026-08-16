"""API contracts for the full terminal lifecycle (V2 F23)."""

from typing import Any

from app.domain.contracts import ContractModel


class TerminalLifecycleSequenceDto(ContractModel):
    run_id: str
    phases: list[str]
    current_phase: str
    chain_status: str
    stage_progress: int
    event_count: int
    next_action: str


class TerminalLifecycleEvidenceDto(ContractModel):
    run_id: str
    events: list[dict[str, Any]]
    seals: list[dict[str, Any]]
    next_action: str


class TerminalLifecycleDriveDto(ContractModel):
    run_id: str
    phases: list[str]
    current_phase: str
    chain_status: str
    stage_progress: int
    event_count: int
    next_action: str
