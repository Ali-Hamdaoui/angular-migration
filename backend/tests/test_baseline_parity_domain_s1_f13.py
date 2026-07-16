import json

from app.domain.baseline_parity import (
    BackendContractSnapshotBuilder,
    BaselineFailureFingerprintService,
    EvidenceConfidence,
    RouteInventoryBuilder,
    anchor_to_dict,
)


def test_failure_fingerprint_is_stable_and_groups_repeated_diagnostics():
    service = BaselineFailureFingerprintService()
    first = service.fingerprint(kind="test", message="FAIL C:\\work\\app.spec.ts:42 expected 1")
    second = service.fingerprint(kind="test", message="fail C:/other/app.spec.ts:99 expected 1")
    assert first.fingerprint == second.fingerprint
    grouped = service.from_diagnostics([{"kind": "test", "message": "FAIL C:\\work\\app.spec.ts:42 expected 1"}] * 2)
    assert len(grouped) == 1
    assert grouped[0].origin == "pre-existing"
    assert grouped[0].count == 2


def test_route_inventory_is_structural_and_machine_proven(tmp_path):
    (tmp_path / "angular.json").write_text(json.dumps({"projects": {"app": {"sourceRoot": "src"}}}), encoding="utf-8")
    source = tmp_path / "src"
    source.mkdir()
    (source / "app.routes.ts").write_text("export const routes = [{ path: 'home' }, { path: 'admin' }];", encoding="utf-8")
    result = RouteInventoryBuilder().build(tmp_path)
    assert result.confidence is EvidenceConfidence.MACHINE_PROVEN
    assert [item["path"] for item in result.value] == ["home", "admin"]


def test_backend_snapshot_exposes_indicators_without_file_contents(tmp_path):
    (tmp_path / "proxy.conf.json").write_text('{"/api": {"target": "https://backend"}}', encoding="utf-8")
    source = tmp_path / "src"
    source.mkdir()
    (source / "auth.interceptor.ts").write_text("const apiUrl = 'https://example.test/api'; export class AuthInterceptor {}", encoding="utf-8")
    result = anchor_to_dict(BackendContractSnapshotBuilder().build(tmp_path))
    assert result["confidence"] == "machine_proven"
    assert result["value"]["api_roots"] == ["https://example.test/api"]
    assert "AuthInterceptor" not in json.dumps(result["value"])

