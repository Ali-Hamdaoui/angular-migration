from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel


class StageStartRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    stage_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")


class StageStartResponse(ContractModel):
    run_id: str
    stage_id: str
    status: str
    plan_checksum: str
    stage_plan_checksum: str
    artifact_set_checksum: str
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
    workspace_fingerprint: str | None = None
