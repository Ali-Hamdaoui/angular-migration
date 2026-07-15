"""Typed API contracts for source runtime resolution."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.domain.execution_profile import ExecutionProfile, RuntimeCandidate

class ExecutionProfileResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    source_angular_exact: str = Field(min_length=1)
    source_typescript_exact: str | None = None
    source_rxjs_exact: str | None = None
    candidates: tuple[RuntimeCandidate, ...] = ()
    validated_at: datetime

class ExecutionProfileSelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    checksum: str = Field(min_length=1)

class ExecutionProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str
    status: str
    policy_version: str
    source_angular_exact: str
    compatible_profiles: tuple[ExecutionProfile, ...] = ()
    selected_profile: ExecutionProfile | None = None
    blockers: tuple[str, ...] = ()
    guidance: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
