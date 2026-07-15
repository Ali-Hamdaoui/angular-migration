import json
from pathlib import Path

from app.workspaces.baseline import BaselineSandboxService


def test_baseline_copy_is_writable_and_excludes_generated_content(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    (snapshot / "node_modules" / "pkg").mkdir(parents=True)
    (snapshot / "src").mkdir(parents=True)
    (snapshot / "src" / "app.ts").write_text("export const app = true;\n", encoding="utf-8")
    (snapshot / "node_modules" / "pkg" / "index.js").write_text("generated", encoding="utf-8")
    fingerprint = "sha256:approved"
    (snapshot / "snapshot-fingerprint.json").write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")

    result = BaselineSandboxService().create(
        run_id="run-1",
        snapshot_root=snapshot,
        baseline_path=tmp_path / "baseline",
        approved_snapshot_fingerprint=fingerprint,
    )

    assert result.input_fingerprint == fingerprint
    assert (result.sandbox_path / "src" / "app.ts").is_file()
    assert not (result.sandbox_path / "node_modules").exists()
    assert (result.sandbox_path / "src" / "app.ts").stat().st_mode & 0o200
