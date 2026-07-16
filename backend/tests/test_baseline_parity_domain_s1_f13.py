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



def test_failure_fingerprint_accepts_one_shot_diagnostics_and_tracks_parser_drift():
    service = BaselineFailureFingerprintService()
    diagnostics = (item for item in [{"kind": "build", "message": "ERROR C:/work/app.ts:7 failed"}])
    grouped = service.from_diagnostics(diagnostics)

    assert grouped[0].count == 1
    assert service.fingerprint(kind="build", message="failed", parser_version="baseline-parsers-v1").fingerprint != service.fingerprint(kind="build", message="failed", parser_version="baseline-parsers-v2").fingerprint


def test_backend_snapshot_redacts_credentials_and_marks_empty_evidence_unknown(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "config.ts").write_text("const apiUrl = 'https://user:super-secret@example.test/api?token=secret';", encoding="utf-8")

    result = anchor_to_dict(BackendContractSnapshotBuilder().build(tmp_path))

    serialized = json.dumps(result["value"])
    assert result["value"]["api_roots"] == ["https://example.test/api"]
    assert "super-secret" not in serialized
    assert "token=secret" not in serialized

    empty = anchor_to_dict(BackendContractSnapshotBuilder().build(tmp_path / "empty"))
    assert empty["confidence"] == "unknown"


def test_empty_route_inventory_is_not_presented_as_machine_proven(tmp_path):
    (tmp_path / "angular.json").write_text(json.dumps({"projects": {"app": {"sourceRoot": "src"}}}), encoding="utf-8")
    (tmp_path / "src").mkdir()

    result = anchor_to_dict(RouteInventoryBuilder().build(tmp_path))

    assert result["value"] == []
    assert result["confidence"] == "unknown"
