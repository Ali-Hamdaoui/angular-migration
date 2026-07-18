"""Run-scoped application contract for deterministic discovery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.domain.discovery import DiscoveryApplicationResult, DiscoveryRequest
from app.services.discovery_service import DiscoveryService


class DiscoveryApplicationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class DiscoveryRunPort(Protocol):
    def resolve_workspace(self, run_id: str, prerequisite_artifact_ids: tuple[str, ...]) -> Path: ...
    def state_version(self, run_id: str) -> int: ...
    def get_idempotent(self, run_id: str, idempotency_key: str) -> tuple[str, DiscoveryApplicationResult] | None: ...
    def save_idempotent(self, run_id: str, idempotency_key: str, request_checksum: str, result: DiscoveryApplicationResult) -> None: ...


class DiscoveryArtifactPort(Protocol):
    def register(self, run_id: str, drafts: tuple) -> tuple[str, ...]: ...


class DiscoveryTransitionPort(Protocol):
    def start(self, request: DiscoveryRequest) -> int: ...
    def complete(self, request: DiscoveryRequest, artifact_ids: tuple[str, ...]) -> int: ...
    def block(self, request: DiscoveryRequest, error_code: str) -> int: ...


@dataclass
class DiscoveryApplicationService:
    run_port: DiscoveryRunPort
    artifact_port: DiscoveryArtifactPort
    transition_port: DiscoveryTransitionPort
    coordinator: DiscoveryService = DiscoveryService()

    def discover(self, request: DiscoveryRequest) -> DiscoveryApplicationResult:
        checksum = self._checksum(request)
        replay = self.run_port.get_idempotent(request.run_id, request.idempotency_key)
        if replay:
            if replay[0] != checksum:
                raise DiscoveryApplicationError("IDEMPOTENCY_KEY_REUSED", "Idempotency key was used with a different payload.")
            return replay[1].model_copy(update={"idempotent_replay": True})
        if self.run_port.state_version(request.run_id) != request.expected_state_version:
            raise DiscoveryApplicationError("STALE_STATE_VERSION", "The run state version is stale.")
        try:
            self.transition_port.start(request)
            workspace = self.run_port.resolve_workspace(request.run_id, request.prerequisite_artifact_ids)
            results, drafts = self.coordinator.discover(workspace)
            artifact_ids = self.artifact_port.register(request.run_id, drafts)
            state_version = self.transition_port.complete(request, artifact_ids)
            result = DiscoveryApplicationResult(run_id=request.run_id, status="completed", state_version=state_version, scanner_results=results, evidence_drafts=drafts, artifact_ids=artifact_ids)
        except DiscoveryApplicationError:
            raise
        except Exception as error:
            state_version = self.transition_port.block(request, "DISCOVERY_DEPENDENCY_FAILED")
            result = DiscoveryApplicationResult(run_id=request.run_id, status="blocked", state_version=state_version, scanner_results=(), evidence_drafts=(), error_code="DISCOVERY_DEPENDENCY_FAILED")
        self.run_port.save_idempotent(request.run_id, request.idempotency_key, checksum, result)
        return result

    @staticmethod
    def _checksum(request: DiscoveryRequest) -> str:
        content = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
