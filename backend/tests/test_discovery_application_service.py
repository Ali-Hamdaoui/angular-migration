import json
from pathlib import Path

import pytest

from app.domain.discovery import DiscoveryApplicationResult, DiscoveryRequest
from app.services.discovery_application_service import DiscoveryApplicationError, DiscoveryApplicationService


class RunPort:
    def __init__(self, workspace: Path, version: int = 4):
        self.workspace, self.version, self.records = workspace, version, {}

    def resolve_workspace(self, run_id, prerequisite_artifact_ids):
        assert prerequisite_artifact_ids == ("artifact-baseline",)
        return self.workspace

    def state_version(self, run_id): return self.version
    def get_idempotent(self, run_id, key): return self.records.get((run_id, key))
    def save_idempotent(self, run_id, key, checksum, result): self.records[(run_id, key)] = (checksum, result)


class Artifacts:
    def __init__(self, fail=False): self.fail = fail
    def register(self, run_id, drafts):
        if self.fail: raise OSError("store unavailable")
        return tuple(f"artifact-{draft.name}" for draft in drafts)


class Transitions:
    def __init__(self): self.calls = []
    def start(self, request): self.calls.append("start"); return request.expected_state_version + 1
    def complete(self, request, artifact_ids): self.calls.append("complete"); return request.expected_state_version + 2
    def block(self, request, error_code): self.calls.append(("block", error_code)); return request.expected_state_version + 2


def request(**overrides):
    payload = {"run_id": "run-1", "expected_state_version": 4, "idempotency_key": "discover-1", "prerequisite_artifact_ids": ("artifact-baseline",), "actor": "operator"}
    payload.update(overrides)
    return DiscoveryRequest(**payload)


def workspace(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "18.2.0", "@angular/material": "18.2.0", "@ngrx/store": "18.0.0"}, "scripts": {"test": "ng test", "lint": "ng lint"}}))
    (tmp_path / "angular.json").write_text(json.dumps({"projects": {"app": {"projectType": "application", "architect": {"build": {"builder": "@angular-devkit/build-angular:application"}}}}}))
    return tmp_path


def test_discovery_is_parallel_deterministic_and_registers_only_canonical_evidence(tmp_path):
    runs, transitions = RunPort(workspace(tmp_path)), Transitions()
    result = DiscoveryApplicationService(runs, Artifacts(), transitions).discover(request())
    assert result.status == "completed"
    assert [item.scanner for item in result.scanner_results] == ["builders", "dependencies", "indicators", "test_lint", "workspace"]
    assert all(item.checksum.startswith("sha256:") for item in result.evidence_drafts)
    assert transitions.calls == ["start", "complete"]


def test_discovery_replays_identical_idempotent_request_and_rejects_changed_payload(tmp_path):
    runs, transitions = RunPort(workspace(tmp_path)), Transitions()
    service = DiscoveryApplicationService(runs, Artifacts(), transitions)
    assert not service.discover(request()).idempotent_replay
    assert service.discover(request()).idempotent_replay
    with pytest.raises(DiscoveryApplicationError, match="different payload") as error:
        service.discover(request(actor="another-operator"))
    assert error.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_discovery_rejects_stale_state_before_side_effects(tmp_path):
    transitions = Transitions()
    service = DiscoveryApplicationService(RunPort(workspace(tmp_path), version=5), Artifacts(), transitions)
    with pytest.raises(DiscoveryApplicationError) as error:
        service.discover(request())
    assert error.value.code == "STALE_STATE_VERSION"
    assert transitions.calls == []


def test_discovery_preserves_a_legal_blocked_result_when_artifact_dependency_fails(tmp_path):
    transitions = Transitions()
    result = DiscoveryApplicationService(RunPort(workspace(tmp_path)), Artifacts(fail=True), transitions).discover(request())
    assert result.status == "blocked"
    assert result.error_code == "DISCOVERY_DEPENDENCY_FAILED"
    assert transitions.calls == ["start", ("block", "DISCOVERY_DEPENDENCY_FAILED")]
