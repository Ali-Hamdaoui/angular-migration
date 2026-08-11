from pathlib import Path

import pytest

from app.services.jest_bootstrap_compatibility_service import (
    LEGACY_JEST_BOOTSTRAPS,
    MODERN_JEST_BOOTSTRAP,
    JestBootstrapCompatibilityError,
    JestBootstrapCompatibilityService,
)
from app.services.patch_apply_service import PatchApplyService
from app.services.stage_preparation_primitives import StageSandboxCopier


def _workspace(tmp_path: Path, setup: str) -> tuple[Path, Path, Path]:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    artifacts = run_root / "artifacts"
    package = workspace / "node_modules" / "jest-preset-angular"
    zone = package / "setup-env" / "zone"
    zone.mkdir(parents=True)
    artifacts.mkdir()
    (workspace / "setup-jest.ts").write_text(setup, encoding="utf-8", newline="")
    (package / "package.json").write_text(
        '{"name":"jest-preset-angular","version":"17.0.0"}', encoding="utf-8"
    )
    (zone / "index.js").write_text(
        "const setupZoneTestEnv = () => {}; module.exports = { setupZoneTestEnv };",
        encoding="utf-8",
    )
    (zone / "index.d.ts").write_text(
        "export declare const setupZoneTestEnv: () => void;", encoding="utf-8"
    )
    return run_root, workspace, artifacts


@pytest.mark.parametrize(
    "legacy",
    [
        statement + line_ending
        for statement in LEGACY_JEST_BOOTSTRAPS
        for line_ending in ("", "\n", "\r\n")
    ],
)
def test_legacy_bootstrap_with_proven_replacement_uses_confined_patch_apply(tmp_path: Path, legacy: str):
    run_root, workspace, artifacts = _workspace(tmp_path, legacy)
    migration = JestBootstrapCompatibilityService().detect(workspace, run_root)

    assert migration is not None
    operation = migration.operation()
    operation["preimage_sha256"] = migration.preimage_sha256
    _prepared, _applied, post_fingerprint = PatchApplyService().apply(
        proposal={"proposal_format": "operations", "operations": [operation], "unified_diff": None},
        workspace_path=str(workspace),
        expected_fingerprint=StageSandboxCopier.fingerprint(workspace),
        run_id="run-1",
        stage_id="stage-1",
        artifact_root=str(artifacts),
        attempt_id="attempt-1",
    )

    assert (workspace / "setup-jest.ts").read_text(encoding="utf-8") == MODERN_JEST_BOOTSTRAP
    assert post_fingerprint == StageSandboxCopier.fingerprint(workspace)


def test_already_modern_bootstrap_is_not_mutated(tmp_path: Path):
    run_root, workspace, _ = _workspace(tmp_path, MODERN_JEST_BOOTSTRAP)
    before = (workspace / "setup-jest.ts").read_bytes()
    assert JestBootstrapCompatibilityService().detect(workspace, run_root) is None
    assert (workspace / "setup-jest.ts").read_bytes() == before


def test_legacy_looking_bootstrap_with_additional_content_is_not_mutated(tmp_path: Path):
    setup = "import 'jest-preset-angular/setup-jest';\nconsole.log('unrelated');\n"
    run_root, workspace, _ = _workspace(tmp_path, setup)
    before = (workspace / "setup-jest.ts").read_bytes()
    assert JestBootstrapCompatibilityService().detect(workspace, run_root) is None
    assert (workspace / "setup-jest.ts").read_bytes() == before


def test_missing_replacement_capability_fails_closed(tmp_path: Path):
    run_root, workspace, _ = _workspace(tmp_path, "import 'jest-preset-angular/setup-jest.js';\n")
    zone = workspace / "node_modules" / "jest-preset-angular" / "setup-env" / "zone"
    (zone / "index.js").unlink()
    before = (workspace / "setup-jest.ts").read_bytes()
    with pytest.raises(JestBootstrapCompatibilityError) as raised:
        JestBootstrapCompatibilityService().detect(workspace, run_root)
    assert raised.value.code == "JEST_BOOTSTRAP_REPLACEMENT_UNAVAILABLE"
    assert (workspace / "setup-jest.ts").read_bytes() == before


def test_commonjs_type_export_proves_modern_bootstrap_api(tmp_path: Path):
    run_root, workspace, _ = _workspace(
        tmp_path, "import 'jest-preset-angular/setup-jest';\n"
    )
    types = workspace / "node_modules" / "jest-preset-angular" / "setup-env" / "zone" / "index.d.ts"
    types.write_text(
        "declare const _default: {\n"
        "  setupZoneTestEnv: (options?: object) => void;\n"
        "};\n"
        "export = _default;\n",
        encoding="utf-8",
    )

    migration = JestBootstrapCompatibilityService().detect(workspace, run_root)

    assert migration is not None
    assert "setupZoneTestEnv" in migration.new_text
