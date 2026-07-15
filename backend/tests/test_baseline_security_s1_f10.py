import json
from pathlib import Path

import pytest

from app.domain.baseline import LifecycleScriptAuditor, PackageMetadataInspector, PackageSourceInventory
from app.workspaces.baseline import BaselineBoundaryError, BaselineSandboxService


def test_dependency_and_lifecycle_evidence_redacts_credentials(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"private": "https://user:super-secret-token@example.test/pkg.tgz"},
        "scripts": {"postinstall": "node setup.js token=another-secret"},
    }), encoding="utf-8")
    package = PackageMetadataInspector().inspect(tmp_path)

    source = PackageSourceInventory().inspect(package)[0]
    script = LifecycleScriptAuditor().inspect(package)[0]
    assert "super-secret-token" not in source.requested
    assert "another-secret" not in script.command
    assert "[redacted]" in source.requested
    assert "[redacted]" in script.command


def test_baseline_alias_cannot_escape_registered_run_root(tmp_path: Path):
    run_root = tmp_path / "run"
    snapshot = run_root / "source-snapshot"
    snapshot.mkdir(parents=True)
    (snapshot / "snapshot-fingerprint.json").write_text(json.dumps({"fingerprint": "sha256:approved"}), encoding="utf-8")

    with pytest.raises(BaselineBoundaryError, match="BASELINE_SANDBOX"):
        BaselineSandboxService().create(
            run_id="run-1",
            snapshot_root=snapshot,
            baseline_path=tmp_path / "outside-baseline",
            approved_snapshot_fingerprint="sha256:approved",
            registered_run_root=run_root,
        )


def test_baseline_and_snapshot_overlap_is_rejected(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "snapshot-fingerprint.json").write_text(json.dumps({"fingerprint": "sha256:approved"}), encoding="utf-8")

    with pytest.raises(BaselineBoundaryError, match="must not overlap"):
        BaselineSandboxService().create(
            run_id="run-1",
            snapshot_root=snapshot,
            baseline_path=snapshot / "baseline",
            approved_snapshot_fingerprint="sha256:approved",
        )
