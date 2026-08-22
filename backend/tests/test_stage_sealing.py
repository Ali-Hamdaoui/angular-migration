import json
from pathlib import Path

import pytest

from app.services.stage_preparation_application_service import StagePreparationApplicationService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.stage_sealing_service import StageSealingError, StageSealingService


def _cleanliness_context(workspace: Path, tmp_path: Path) -> dict[str, object]:
    fingerprint = StageSandboxCopier.fingerprint(workspace)
    return {
        "run_id": "run-1",
        "stage_id": "stage-1",
        "stage_plan_checksum": "sha256:plan",
        "workspace_path": str(workspace),
        "workspace_fingerprint": fingerprint,
        "g09_workspace_fingerprint": fingerprint,
        "artifact_root": str(tmp_path / "artifacts" / "run-1"),
        "stage_root": str(tmp_path / "stages"),
        "g09_package_checksum": "sha256:g09",
        "previous_chain_hash": "genesis",
        "validation_summary_checksum": "sha256:validation",
        "evidence_index": [],
    }


def test_stage_seal_is_atomic_chain_bound_and_excludes_generated_dependencies(tmp_path: Path):
    workspace = tmp_path / "stages" / "stage-1"
    artifacts = tmp_path / "artifacts" / "run-1"
    workspace.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    (workspace / "package.json").write_text('{"dependencies":{}}', encoding="utf-8")
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "generated.js").write_text("generated", encoding="utf-8")
    for relative in (
        "node_modules/node-gyp/test/fixtures/server.key",
        "node_modules/agent-base/test/ssl-cert-snakeoil.key",
        "node_modules/agent-base/test/ssl-cert-snakeoil.pem",
    ):
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("dependency fixture", encoding="utf-8")
    service = StageSealingService()
    context = {
        "run_id": "run-1",
        "stage_id": "stage-1",
        "stage_plan_checksum": "sha256:plan",
        "workspace_path": str(workspace),
        "workspace_fingerprint": StageSandboxCopier.fingerprint(workspace),
        "artifact_root": str(artifacts),
        "stage_root": str(tmp_path / "stages"),
        "g09_package_checksum": "sha256:g09",
        "g09_workspace_fingerprint": StageSandboxCopier.fingerprint(workspace),
        "previous_chain_hash": "genesis",
        "validation_summary_checksum": "sha256:validation",
        "evidence_index": [],
    }

    target, fingerprint, chain, output, seal = service.seal(context, "sha256:g12")
    replay = service.seal(context, "sha256:g12")

    assert target == replay[0]
    assert fingerprint == replay[1] == StageSandboxCopier.fingerprint(target)
    assert chain == replay[2]
    assert not (target / "node_modules").exists()
    manifest = json.loads(output.content)
    assert (target / "package.json").exists()
    assert all(not item["path"].startswith("node_modules/") for item in manifest["files"])
    assert output.ref.checksum and seal.ref.checksum
    next_stage = StagePreparationApplicationService().prepare(
        {
            "BASELINE_SANDBOX": str(target),
            "STAGE_SANDBOX": str(tmp_path / "next-stages"),
        },
        "stage-2",
    )
    assert next_stage.fingerprint == fingerprint


def test_cleanliness_ignores_dependency_owned_secret_fixtures(tmp_path: Path):
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.ts").write_text("export const app = true", encoding="utf-8")
    for relative in (
        "node_modules/node-gyp/test/fixtures/server.key",
        "node_modules/agent-base/test/ssl-cert-snakeoil.key",
        "node_modules/agent-base/test/ssl-cert-snakeoil.pem",
    ):
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("dependency fixture", encoding="utf-8")

    result = StageSealingService().verify_cleanliness(_cleanliness_context(workspace, tmp_path))

    assert result["status"] == "clean"


@pytest.mark.parametrize(
    "relative",
    (
        "src/server.key",
        "certs/private.pem",
        ".env",
        "certificates/client.pfx",
    ),
)
def test_cleanliness_rejects_project_owned_secret_paths(tmp_path: Path, relative: str):
    workspace = tmp_path / "workspace"
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("project secret", encoding="utf-8")

    with pytest.raises(StageSealingError) as error:
        StageSealingService().verify_cleanliness(_cleanliness_context(workspace, tmp_path))

    assert error.value.code == "STAGE_CLEANLINESS_FAILED"


def test_stage_fingerprint_changes_for_included_project_file(tmp_path: Path):
    workspace = tmp_path / "workspace"
    (workspace / "src" / "app").mkdir(parents=True)
    file = workspace / "src" / "app" / "app.component.ts"
    file.write_text("before", encoding="utf-8")
    before = StageSandboxCopier.fingerprint(workspace)

    file.write_text("after", encoding="utf-8")

    assert StageSandboxCopier.fingerprint(workspace) != before


def test_successor_reconstruction_uses_sealed_output_and_is_idempotent(tmp_path: Path):
    sealed = tmp_path / "stages" / ".sealed" / "stage-1"
    target = tmp_path / "stages" / "stage-2"
    sealed.mkdir(parents=True)
    (sealed / "package.json").write_text('{"version":1}', encoding="utf-8")
    fingerprint = StageSandboxCopier.fingerprint(sealed)
    target.mkdir()
    (target / "package.json").write_text('{"version":"mutated"}', encoding="utf-8")

    aliases = {
        "BASELINE_SANDBOX": str(sealed),
        "STAGE_SANDBOX": str(tmp_path / "stages"),
    }
    service = StagePreparationApplicationService()
    first = service.prepare(aliases, "stage-2", expected_fingerprint=fingerprint).fingerprint
    second = service.prepare(aliases, "stage-2", expected_fingerprint=fingerprint).fingerprint

    assert first == second == fingerprint
    assert (target / "package.json").read_text(encoding="utf-8") == '{"version":1}'


def test_successor_reconstruction_rejects_corrupt_sealed_output(tmp_path: Path):
    sealed = tmp_path / "stages" / ".sealed" / "stage-1"
    sealed.mkdir(parents=True)
    (sealed / "package.json").write_text("sealed", encoding="utf-8")
    target = tmp_path / "stages" / "stage-2"
    target.mkdir()
    with pytest.raises(Exception, match="fingerprint"):
        StagePreparationApplicationService().prepare(
            {
                "BASELINE_SANDBOX": str(sealed),
                "STAGE_SANDBOX": str(tmp_path / "stages"),
            },
            "stage-2",
            expected_fingerprint="sha256:" + "0" * 64,
            expected_source_fingerprint="sha256:" + "0" * 64,
        )


def test_stage_seal_rejects_workspace_before_copy_when_target_major_is_wrong(tmp_path: Path):
    workspace = tmp_path / "stages" / "stage-12-to-13"
    artifacts = tmp_path / "artifacts" / "run-1"
    workspace.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    (workspace / "package.json").write_text(
        '{"dependencies":{"@angular/core":"~12.0.0"}}', encoding="utf-8"
    )
    (workspace / "package-lock.json").write_text(
        '{"packages":{"":{"dependencies":{"@angular/core":"~12.0.0"}},'
        '"node_modules/@angular/core":{"version":"12.0.5"}}}',
        encoding="utf-8",
    )
    fingerprint = StageSandboxCopier.fingerprint(workspace)
    context = {
        "run_id": "run-1",
        "stage_id": "stage-12-to-13",
        "stage_plan": {"target_exact": "13.0.0"},
        "workspace_path": str(workspace),
        "workspace_fingerprint": fingerprint,
        "artifact_root": str(artifacts),
        "stage_root": str(tmp_path / "stages"),
        "g09_package_checksum": "sha256:g09",
        "g09_workspace_fingerprint": fingerprint,
        "previous_chain_hash": "genesis",
        "validation_summary_checksum": "sha256:validation",
        "evidence_index": [],
    }

    with pytest.raises(Exception, match="completed stage target"):
        StageSealingService().seal(context, "sha256:g12")

    assert not (tmp_path / "stages" / ".sealed").exists()
