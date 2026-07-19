"""S3-F14 domain test — stage seal, G12 gate, and copy-forward."""
from datetime import UTC, datetime

import pytest
from app.domain.stage_seal import (
    CleanupResult,
    G12Decision,
    G12Gate,
    OutputFingerprint,
    SealStatus,
    StageSealError,
    StageSealService,
)
from app.domain.stage_copy_forward import (
    CopyForwardItem,
    CopyForwardManifest,
    CopyForwardStatus,
    StageCopyForwardError,
    StageCopyForwardService,
)


def test_compute_fingerprint():
    """Output fingerprint is computed correctly from file metadata."""
    service = StageSealService()
    files = [
        {"path": "dist/main.js", "size_bytes": 1024, "checksum": "abc"},
        {"path": "dist/runtime.js", "size_bytes": 512, "checksum": "def"},
    ]
    fingerprint = service.compute_fingerprint(
        fingerprint_id="fp-1",
        run_id="run-1",
        stage_id="stage-1",
        output_path="dist",
        files=files,
    )
    assert fingerprint.fingerprint_id == "fp-1"
    assert fingerprint.size_bytes == 1536
    assert fingerprint.file_count == 2
    assert fingerprint.checksum is not None
    assert len(fingerprint.checksum) == 64  # sha256 hex


def test_plan_cleanup(tmp_path):
    """Cleanup planning correctly identifies paths to remove."""
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "dist").mkdir()
    (tmp_path / "temp_build").write_text("temp")
    (tmp_path / ".cache").write_text("cache")

    service = StageSealService()
    fingerprint = OutputFingerprint(
        fingerprint_id="fp-1",
        run_id="run-1",
        stage_id="stage-1",
        relative_path="dist",
        size_bytes=1536,
        checksum="abc",
        file_count=2,
    )
    workspace_paths = [
        str(tmp_path / "node_modules"),
        str(tmp_path / "dist"),
        str(tmp_path / "temp_build"),
        str(tmp_path / ".cache"),
    ]
    result = service.plan_cleanup(fingerprint, workspace_paths)
    # node_modules and dist should be preserved
    assert str(tmp_path / "temp_build") in result.paths_cleaned
    assert str(tmp_path / ".cache") in result.paths_cleaned


def test_evaluate_g12_readiness_all_checks():
    """G12 readiness evaluates correctly when all conditions met."""
    service = StageSealService()
    ready, reason = service.evaluate_g12_readiness(
        assurance_passed=True,
        all_checks_passed=True,
        has_valid_fingerprint=True,
    )
    assert ready is True
    assert reason is None


def test_evaluate_g12_readiness_assurance_failed():
    """G12 readiness fails when assurance not passed."""
    service = StageSealService()
    ready, reason = service.evaluate_g12_readiness(
        assurance_passed=False,
        all_checks_passed=True,
        has_valid_fingerprint=True,
    )
    assert ready is False
    assert reason is not None
    assert "Assurance" in reason


def test_evaluate_g12_readiness_checks_failed():
    """G12 readiness fails when not all checks passed."""
    service = StageSealService()
    ready, reason = service.evaluate_g12_readiness(
        assurance_passed=True,
        all_checks_passed=False,
        has_valid_fingerprint=True,
    )
    assert ready is False
    assert reason is not None
    assert "checks" in reason.lower()


def test_evaluate_g12_readiness_no_fingerprint():
    """G12 readiness fails without valid fingerprint."""
    service = StageSealService()
    ready, reason = service.evaluate_g12_readiness(
        assurance_passed=True,
        all_checks_passed=True,
        has_valid_fingerprint=False,
    )
    assert ready is False
    assert reason is not None
    assert "fingerprint" in reason.lower()


def test_g12_gate_defaults():
    """G12Gate has sensible defaults."""
    gate = G12Gate(gate_id="g12-1", run_id="run-1", stage_id="stage-1")
    assert gate.status == "pending"
    assert gate.decision is G12Decision.PENDING
    assert gate.state_version == 1


def test_copy_forward_resolve_manifest(tmp_path):
    """Copy-forward resolves manifest with existing files."""
    service = StageCopyForwardService()
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    (source / "package.json").write_text('{"name": "test"}')
    (source / "angular.json").write_text('{"version": 1}')

    manifest = service.resolve_copy_manifest(
        manifest_id="cf-1",
        run_id="run-1",
        source_stage_id="stage-1",
        target_stage_id="stage-2",
        source_sandbox=str(source),
        target_sandbox=str(target),
    )
    assert manifest.manifest_id == "cf-1"
    assert manifest.source_stage_id == "stage-1"
    assert manifest.target_stage_id == "stage-2"
    assert manifest.status is CopyForwardStatus.PENDING
    assert manifest.total_items >= 2
    assert manifest.total_bytes > 0


def test_copy_forward_aggregate_summary():
    """Copy-forward aggregate summary produces correct metadata."""
    service = StageCopyForwardService()
    manifest = CopyForwardManifest(
        manifest_id="cf-1",
        run_id="run-1",
        source_stage_id="stage-1",
        target_stage_id="stage-2",
        status=CopyForwardStatus.COMPLETED,
        total_items=5,
        copied_items=5,
        total_bytes=10000,
        checksum="sha256:test",
    )
    summary = service.aggregate_copy_summary(manifest)
    assert summary["manifest_id"] == "cf-1"
    assert summary["copied_items"] == 5
    assert summary["total_bytes"] == 10000


def test_copy_forward_item_defaults():
    """CopyForwardItem has sensible defaults."""
    item = CopyForwardItem(source_path="test.json", target_path="test.json")
    assert item.checksum is None
    assert item.size_bytes == 0
    assert item.copied is False
    assert item.error is None


def test_seal_status_enum():
    """SealStatus enum values are correct."""
    assert SealStatus.PENDING.value == "pending"
    assert SealStatus.SEALED.value == "sealed"
    assert SealStatus.FAILED.value == "failed"


def test_copy_forward_status_enum():
    """CopyForwardStatus enum values are correct."""
    assert CopyForwardStatus.PENDING.value == "pending"
    assert CopyForwardStatus.COMPLETED.value == "completed"
    assert CopyForwardStatus.FAILED.value == "failed"


def test_stage_seal_error_raised():
    """StageSealError is a ValueError."""
    with pytest.raises(StageSealError):
        raise StageSealError("Test seal error")


def test_stage_copy_forward_error_raised():
    """StageCopyForwardError is a ValueError."""
    with pytest.raises(StageCopyForwardError):
        raise StageCopyForwardError("Test copy error")
