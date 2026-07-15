"""Typed contracts for persisted source snapshots."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.domain.contracts import ArtifactRefDto, ContractModel


class SnapshotStatus(str, Enum):
    STARTED = "started"
    CREATED = "created"
    FAILED = "failed"


class CreateSourceSnapshotRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)


class SourceSnapshotDto(ContractModel):
    snapshot_id: str
    run_id: str
    status: SnapshotStatus
    source_path: str
    snapshot_path: str
    manifest_id: str | None = None
    fingerprint: str | None = None
    policy_version: str
    file_count: int = Field(default=0, ge=0)
    total_size_bytes: int = Field(default=0, ge=0)
    exclusions: list[dict[str, str]] = Field(default_factory=list)
    git_metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactRefDto] = Field(default_factory=list)
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    idempotent_replay: bool = False
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
