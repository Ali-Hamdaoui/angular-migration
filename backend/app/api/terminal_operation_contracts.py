"""API contracts for terminal operation (V2 F06)."""

from typing import Any

from app.domain.contracts import ContractModel


class TerminalNextActionDto(ContractModel):
    run_id: str
    status: str
    next_permitted_action: str
    remaining_work: list[str]
    gate: dict[str, Any]


class TerminalDiagnosticsDto(ContractModel):
    run_id: str
    diagnostic_packs: list[str]
    failure_groups: list[dict[str, Any]]
    root_causes: dict[str, Any]


class TerminalResumeDto(ContractModel):
    run_id: str
    chain_status: str
    next: dict[str, Any]


class TerminalActionRequest(ContractModel):
    actor: str | None = None
