"""Authoritative application seam for S2-F02-I01 parity-baseline discovery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.domain.parity_baseline import ParityBaselineBuilder, ParityBaselineResult


class ParityBaselineRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    prerequisite_artifact_ids: tuple[str, ...] = Field(min_length=1)
    actor: str = Field(min_length=1, max_length=128)


class ParityBaselineApplicationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    status: str
    state_version: int
    baseline: ParityBaselineResult | None = None
    artifact_ids: tuple[str, ...] = ()
    error_code: str | None = None
    idempotent_replay: bool = False


class ParityBaselineApplicationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ParityBaselineRunPort(Protocol):
    def resolve_workspace(self, run_id: str, prerequisite_artifact_ids: tuple[str, ...]) -> Path: ...
    def state_version(self, run_id: str) -> int: ...
    def get_idempotent(
        self, run_id: str, idempotency_key: str
    ) -> tuple[str, ParityBaselineApplicationResult] | None: ...
    def save_idempotent(
        self, run_id: str, idempotency_key: str, request_checksum: str, result: ParityBaselineApplicationResult
    ) -> None: ...


class ParityBaselineArtifactPort(Protocol):
    def register(self, run_id: str, drafts: tuple) -> tuple[str, ...]: ...


class ParityBaselineTransitionPort(Protocol):
    def start(self, request: ParityBaselineRequest) -> int: ...
    def complete(self, request: ParityBaselineRequest, artifact_ids: tuple[str, ...]) -> int: ...
    def block(self, request: ParityBaselineRequest, error_code: str) -> int: ...


@dataclass
class ParityBaselineApplicationService:
    run_port: ParityBaselineRunPort
    artifact_port: ParityBaselineArtifactPort
    transition_port: ParityBaselineTransitionPort
    builder: ParityBaselineBuilder = ParityBaselineBuilder()

    def inspect(self, request: ParityBaselineRequest) -> ParityBaselineApplicationResult:
        checksum = self._checksum(request)
        replay = self.run_port.get_idempotent(request.run_id, request.idempotency_key)
        if replay:
            if replay[0] != checksum:
                raise ParityBaselineApplicationError(
                    "IDEMPOTENCY_KEY_REUSED", "Idempotency key was used with a different payload."
                )
            return replay[1].model_copy(update={"idempotent_replay": True})
        if self.run_port.state_version(request.run_id) != request.expected_state_version:
            raise ParityBaselineApplicationError("STALE_STATE_VERSION", "The run state version is stale.")
        baseline: ParityBaselineResult | None = None
        try:
            self.transition_port.start(request)
            workspace = self.run_port.resolve_workspace(request.run_id, request.prerequisite_artifact_ids)
            baseline = self.builder.build(workspace)
            artifact_ids = self.artifact_port.register(request.run_id, baseline.evidence_drafts)
            result = ParityBaselineApplicationResult(
                run_id=request.run_id,
                status="completed",
                state_version=self.transition_port.complete(request, artifact_ids),
                baseline=baseline,
                artifact_ids=artifact_ids,
            )
        except ParityBaselineApplicationError:
            raise
        except Exception:
            result = ParityBaselineApplicationResult(
                run_id=request.run_id,
                status="blocked",
                state_version=self.transition_port.block(request, "PARITY_BASELINE_DEPENDENCY_FAILED"),
                baseline=baseline,
                error_code="PARITY_BASELINE_DEPENDENCY_FAILED",
            )
        self.run_port.save_idempotent(request.run_id, request.idempotency_key, checksum, result)
        return result

    @staticmethod
    def _checksum(request: ParityBaselineRequest) -> str:
        content = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
