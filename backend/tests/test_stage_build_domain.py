"""S3-F11 domain test — stage build matrix."""
from pathlib import Path

import pytest
from app.domain.stage_build import (
    BuildResult,
    BuildTarget,
    BuildTargetKind,
    BuildTargetStatus,
    StageBuildError,
    StageBuildService,
)


def test_resolve_targets_without_angular_json(tmp_path: Path) -> None:
    """Build targets are resolved from sandbox when angular.json is missing."""
    sandbox = tmp_path / "stage_build" / "no-angular"
    sandbox.mkdir(parents=True, exist_ok=True)
    service = StageBuildService()
    targets = service.resolve_targets(sandbox)
    assert len(targets) > 0
    assert all(isinstance(t, BuildTarget) for t in targets)
    assert any(t.kind == BuildTargetKind.APPLICATION for t in targets)


def test_resolve_targets_with_angular_json(tmp_path: Path) -> None:
    """Build targets are resolved from angular.json when present."""
    sandbox = tmp_path / "sandbox_angular"
    sandbox.mkdir(parents=True)
    (sandbox / "angular.json").write_text('{"version": 1, "projects": {"app": {"projectType": "application"}}}')
    service = StageBuildService()
    targets = service.resolve_targets(sandbox)
    assert len(targets) >= 1


def test_aggregate_matrix_summary_all_passed():
    """Aggregate summary correctly counts passed builds."""
    service = StageBuildService()
    results = [
        BuildResult(target_id="t1", kind=BuildTargetKind.APPLICATION, status=BuildTargetStatus.PASSED, exit_code=0, duration_ms=10000),
        BuildResult(target_id="t2", kind=BuildTargetKind.LIBRARY, status=BuildTargetStatus.PASSED, exit_code=0, duration_ms=5000),
    ]
    summary = service.aggregate_matrix_summary(results)
    assert summary["target_count"] == 2
    assert summary["passed"] == 2
    assert summary["failed"] == 0


def test_aggregate_matrix_summary_mixed():
    """Aggregate summary correctly handles mixed results."""
    service = StageBuildService()
    results = [
        BuildResult(target_id="t1", kind=BuildTargetKind.APPLICATION, status=BuildTargetStatus.PASSED, exit_code=0),
        BuildResult(target_id="t2", kind=BuildTargetKind.LIBRARY, status=BuildTargetStatus.FAILED, exit_code=1),
        BuildResult(target_id="t3", kind=BuildTargetKind.E2E, status=BuildTargetStatus.SKIPPED),
    ]
    summary = service.aggregate_matrix_summary(results)
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["blocked"] == 0


def test_build_target_defaults():
    """BuildTarget has sensible defaults."""
    target = BuildTarget(target_id="test-target", kind=BuildTargetKind.APPLICATION)
    assert target.executable == "npx"
    assert target.arguments == ("ng", "build")
    assert target.supported is True
    assert target.blocker is None


def test_build_result_defaults():
    """BuildResult has sensible defaults."""
    result = BuildResult(target_id="test-target", kind=BuildTargetKind.APPLICATION, status=BuildTargetStatus.PENDING)
    assert result.exit_code is None
    assert result.duration_ms is None
    assert result.warnings == ()


def test_stage_build_error_raised():
    """StageBuildError is a ValueError."""
    with pytest.raises(StageBuildError):
        raise StageBuildError("Test build error")
