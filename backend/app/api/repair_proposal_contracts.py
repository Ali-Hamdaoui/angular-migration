"""Typed HTTP contracts for the repair proposal and G10 approval surface."""

from pydantic import Field

from app.domain.contracts import ContractModel
from app.domain.repair_proposal import G10Decision, G10Status, ProposalStatus


class RepairProposalDto(ContractModel):
    """API response shape for a repair proposal read."""

    proposal_id: str
    failure_id: str
    context_pack_id: str
    proposer_invocation_id: str
    status: ProposalStatus
    summary: str | None = None
    root_cause: str | None = None
    fix_strategy: str | None = None
    diff_checksum: str
    changed_files: list[str]
    workspace_fingerprint: str
    risk_notes: list[str] = []
    g10_status: G10Status = G10Status.PENDING
    g10_decision: str | None = None
    g10_approval_id: str | None = None
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)


class G10DecisionRequestDto(ContractModel):
    """API input for a G10 decision."""

    proposal_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    decision: G10Decision
    rationale: str | None = Field(default=None, max_length=4000)
    workspace_fingerprint: str = Field(min_length=1)
    diff_checksum: str = Field(min_length=1)
    lineage_checksum: str = Field(min_length=1)


class G10DecisionResponseDto(ContractModel):
    """API response for a G10 decision."""

    run_id: str
    proposal_id: str
    decision: G10Decision
    accepted: bool
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    idempotent_replay: bool = False
    stale: bool = False
    reason: str | None = None
