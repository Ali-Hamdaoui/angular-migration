from pydantic import Field

from app.domain.contracts import ContractModel


class BaselineRepairRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    recipe_id: str = Field(pattern="^BASELINE-TEST-001$")
    g03_package_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class BaselineRepairResponse(ContractModel):
    run_id: str
    recipe_id: str
    attempt_id: str
    status: str
    g03_package_checksum: str
    proposal_checksum: str
    pre_fingerprint: str
    post_fingerprint: str
    artifact_ids: list[str]
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
