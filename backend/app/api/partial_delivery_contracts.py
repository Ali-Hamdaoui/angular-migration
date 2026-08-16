"""API contracts for partial migration delivery (V2 F26)."""

from datetime import datetime

from app.domain.contracts import ContractModel


class PartialDeliveryDecisionDto(ContractModel):
    run_id: str
    delivered_at_stage: int | None = None
    delivered_fingerprint: str
    validated: bool
    remaining_stages: list[str]
    resumable: bool
    checksum: str


class PartialDeliveryRecordDto(ContractModel):
    id: str
    run_id: str
    delivered_at_stage: int | None = None
    delivered_fingerprint: str
    validated: bool
    remaining_stages: list[str]
    resumable: bool
    blockers: list[str]
    checksum: str
    created_at: datetime


class PartialDeliveryListDto(ContractModel):
    deliveries: list[PartialDeliveryRecordDto]


class PartialDeliveryResumeDto(ContractModel):
    run_id: str
    delivered_at_stage: int | None = None
    remaining_stages: list[str]
    resume_action: str


class PartialDeliveryRequest(ContractModel):
    workspace_path: str
