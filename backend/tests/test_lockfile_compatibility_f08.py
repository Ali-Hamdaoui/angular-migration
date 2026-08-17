"""Tests for F08 lockfile compatibility validation and evidence."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.lockfile_compatibility import (
    LockfileDependencySet,
    evaluate_lockfile_compatibility,
    version_satisfies,
)
from app.repositories.models import LockfileGenerationEvidenceModel, MigrationRunModel, MigrationStageModel
from app.repositories.session import session_scope
from app.services.lockfile_compatibility_service import (
    LockfileCompatibilityError,
    LockfileCompatibilityService,
)

NOW = datetime.now(UTC)


FULL_DEPS = {
    "typescript": "5.5.4",
    "rxjs": "7.8.1",
    "zone.js": "0.14.0",
    "@angular/core": "19.0.0",
    "@angular/cli": "19.0.0",
}


def write_lockfile(workspace: Path, *, deps: dict[str, str] | None = None, root_deps: dict[str, str] | None = None) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    packages: dict = {"": {"dependencies": root_deps or {}}}
    for name, version in (deps or {}).items():
        packages[f"node_modules/{name}"] = {"version": version}
    path = workspace / "package-lock.json"
    path.write_text(json.dumps({"name": "app", "lockfileVersion": 3, "packages": packages}, indent=2))
    return path


def test_version_satisfies_semantics():
    assert version_satisfies("5.5.4", "5.5.4") is True
    assert version_satisfies("5.5.4", "5.6.0") is False
    assert version_satisfies("5.5.4", None, minimum="5.5.0") is True
    assert version_satisfies("5.4.0", None, minimum="5.5.0") is False
    assert version_satisfies(None, "5.5.4") is False


def test_evaluate_compatibility_verdict():
    dependency_set = LockfileDependencySet(
        root_dependencies={},
        resolved_packages={"typescript": "5.5.4", "@angular/core": "19.0.0"},
        checksum="sha256:x",
    )
    verdict = evaluate_lockfile_compatibility(
        dependency_set,
        source_family="angular-18.x",
        target_family="angular-19.x",
        catalogue_expected={"@angular/core": "19.0.0", "typescript": None},
        catalogue_minimums={"typescript": "5.5.0"},
    )
    assert verdict.status == "valid"
    assert all(f.status == "ok" for f in verdict.findings)


def test_evaluate_compatibility_rejects_mismatch_and_missing():
    dependency_set = LockfileDependencySet(
        root_dependencies={},
        resolved_packages={"typescript": "5.4.0"},
        checksum="sha256:x",
    )
    verdict = evaluate_lockfile_compatibility(
        dependency_set,
        source_family="angular-18.x",
        target_family="angular-19.x",
        catalogue_expected={"@angular/core": "19.0.0", "typescript": None},
        catalogue_minimums={"typescript": "5.5.0"},
    )
    assert verdict.status == "blocked"
    codes = {b.split(":")[0] for b in verdict.blockers}
    assert "LOCKFILE_VERSION_INCOMPATIBLE" in codes
    assert "LOCKFILE_DEPENDENCY_MISSING" in codes


def test_inspect_lockfile_parses_dependency_set(tmp_path: Path):
    workspace = tmp_path / "ws"
    write_lockfile(workspace, deps={"typescript": "5.5.4", "@angular/core": "19.0.0"}, root_deps={"@angular/core": "19.0.0"})
    service = LockfileCompatibilityService()
    dependency_set = service.inspect_lockfile(workspace)
    assert dependency_set.resolved_version("typescript") == "5.5.4"
    assert dependency_set.resolved_version("@angular/core") == "19.0.0"
    assert dependency_set.checksum.startswith("sha256:")
    assert dependency_set.lockfile_version == 3


def test_validate_stage_lockfile_against_catalogue(tmp_path: Path):
    workspace = tmp_path / "ws"
    write_lockfile(workspace, deps=dict(FULL_DEPS))
    service = LockfileCompatibilityService()
    verdict = service.validate_stage_lockfile(workspace, "angular-18.x", "angular-19.x")
    assert verdict.status == "valid"
    assert verdict.target_family == "angular-19.x"


def test_validate_stage_lockfile_unknown_entry_raises(tmp_path: Path):
    workspace = tmp_path / "ws"
    write_lockfile(workspace, deps={})
    service = LockfileCompatibilityService()
    with pytest.raises(LockfileCompatibilityError) as exc:
        service.validate_stage_lockfile(workspace, "angular-30.x", "angular-31.x")
    assert exc.value.code == "CATALOGUE_ENTRY_MISSING"


def _seed(run_id: str, stage_id: str) -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family="angular-18.x", target_version_family="angular-19.x",
                                        status="planned", created_at=NOW))
        session.commit()


def test_record_and_list_lockfile_evidence(tmp_path: Path):
    run_id = f"run-f08-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    _seed(run_id, stage_id)
    workspace = tmp_path / "ws"
    write_lockfile(workspace, deps=dict(FULL_DEPS))
    service = LockfileCompatibilityService()
    verdict = service.validate_stage_lockfile(workspace, "angular-18.x", "angular-19.x")
    row = service.record_evidence(
        run_id=run_id, stage_id=stage_id, workspace=workspace, verdict=verdict,
        node_version="20.20.2", npm_version="10.8.2", node_sha256="a" * 64, npm_sha256="b" * 64,
        execution_id="exec-f08", deterministic=True,
    )
    assert row.validation_status == "valid"
    assert row.node_version == "20.20.2"
    assert row.lockfile_checksum.startswith("sha256:")

    listed = service.list_stage_evidence(run_id, stage_id)
    assert len(listed) == 1
    with session_scope() as session:
        assert session.query(LockfileGenerationEvidenceModel).filter_by(run_id=run_id).count() == 1


def test_record_evidence_unknown_run_raises(tmp_path: Path):
    workspace = tmp_path / "ws"
    write_lockfile(workspace, deps=dict(FULL_DEPS))
    service = LockfileCompatibilityService()
    verdict = service.validate_stage_lockfile(workspace, "angular-18.x", "angular-19.x")
    with pytest.raises(LockfileCompatibilityError) as exc:
        service.record_evidence(run_id="run-missing", stage_id="stage-missing", workspace=workspace, verdict=verdict)
    assert exc.value.code == "RUN_NOT_FOUND"


def test_inspect_v1_lockfile_format(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    v1 = {
        "name": "app", "version": "1.0.0", "lockfileVersion": 1,
        "dependencies": {
            "typescript": {"version": "5.5.4"},
            "@angular/core": {"version": "19.0.0", "dependencies": {"rxjs": {"version": "7.8.1"}}},
        },
    }
    (workspace / "package-lock.json").write_text(json.dumps(v1))
    service = LockfileCompatibilityService()
    dependency_set = service.inspect_lockfile(workspace)
    assert dependency_set.resolved_version("typescript") == "5.5.4"
    assert dependency_set.resolved_version("@angular/core") == "19.0.0"
    assert dependency_set.resolved_version("rxjs") == "7.8.1"
    assert dependency_set.lockfile_version == 1
    assert service.detect_lockfile_format(v1) == "v1"
    assert service.resolve_package_version(v1, "@angular/core") == "19.0.0"
    assert service.resolve_package_version(v1, "rxjs") == "7.8.1"


@pytest.mark.parametrize("version", (1, 2, 3))
def test_supported_lockfile_formats_are_detected(version):
    assert LockfileCompatibilityService.detect_lockfile_format({"lockfileVersion": version}) == f"v{version}"
    assert LockfileCompatibilityService.detect_lockfile_format({"lockfileVersion": 99}) is None


def test_unsupported_lockfile_version_fails_closed(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "package-lock.json").write_text('{"lockfileVersion":99}', encoding="utf-8")
    verdict = LockfileCompatibilityService().validate_stage_lockfile(workspace, "angular-18.x", "angular-19.x")
    assert verdict.status == "blocked"
    assert verdict.blockers == ("LOCKFILE_FORMAT_UNSUPPORTED",)


def test_inspect_malformed_lockfile_hashes_raw_bytes(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "package-lock.json").write_text("not json{{{")
    service = LockfileCompatibilityService()
    dependency_set = service.inspect_lockfile(workspace)
    assert dependency_set.checksum.startswith("sha256:")
    assert dependency_set.checksum != "missing"


def test_record_evidence_with_runtime_binding(tmp_path: Path):
    run_id = f"run-f08b-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    _seed(run_id, stage_id)
    workspace = tmp_path / "ws"
    write_lockfile(workspace, deps=dict(FULL_DEPS))
    service = LockfileCompatibilityService()
    verdict = service.validate_stage_lockfile(workspace, "angular-18.x", "angular-19.x")
    row = service.record_evidence(
        run_id=run_id, stage_id=stage_id, workspace=workspace, verdict=verdict,
        execution_id="exec-f08b", node_version="20.20.2", npm_version="10.8.2",
        node_sha256="c" * 64, npm_sha256="d" * 64, deterministic=True,
    )
    assert row.node_version == "20.20.2"
    assert row.execution_id == "exec-f08b"
    assert row.deterministic is True
