from pathlib import Path

from app.services.stage_preparation_application_service import StagePreparationApplicationService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.stage_sealing_service import StageSealingService


def test_stage_seal_is_atomic_chain_bound_and_excludes_generated_dependencies(tmp_path: Path):
    workspace = tmp_path / "stages" / "stage-1"
    artifacts = tmp_path / "artifacts" / "run-1"
    workspace.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    (workspace / "package.json").write_text('{"dependencies":{}}', encoding="utf-8")
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "generated.js").write_text("generated", encoding="utf-8")
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
    assert output.ref.checksum and seal.ref.checksum
    next_stage = StagePreparationApplicationService().prepare(
        {
            "BASELINE_SANDBOX": str(target),
            "STAGE_SANDBOX": str(tmp_path / "next-stages"),
        },
        "stage-2",
    )
    assert next_stage.fingerprint == fingerprint
