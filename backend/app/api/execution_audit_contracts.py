"""API contracts for the immutable execution audit trail (V2 F27-03)."""

from datetime import datetime

from app.domain.contracts import ContractModel


class ExecutionAuditEntryDto(ContractModel):
    id: str
    run_id: str
    stage_id: str | None = None
    execution_id: str | None = None
    command_id: str
    command_class: str
    event: str
    actor: str | None = None
    executable: str
    arguments: list[str]
    policy_version: str
    state_version: int | None = None
    network_profile: str | None = None
    reason: str
    prev_checksum: str
    checksum: str
    occurred_at: datetime


class ExecutionAuditListDto(ContractModel):
    entries: list[ExecutionAuditEntryDto]


class ExecutionAuditVerificationDto(ContractModel):
    run_id: str
    entries: int
    verified: int
    intact: bool
    first_broken_entry: str | None = None
    tail_checksum: str
