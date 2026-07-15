"""Request contract for creating a pending G02 review package."""

from pydantic import Field

from app.domain.contracts import ContractModel


class G02PackageInitializationRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    gate_id: str = Field(default="G02", min_length=1, max_length=16)
