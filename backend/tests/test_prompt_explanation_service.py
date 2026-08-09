from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    LlmInvocationModel,
    MigrationRunModel,
    StageCheckpointModel,
)
from app.services.prompt_explanation_service import PromptExplanationService
from app.services.transformer_prompt_service import AngularPromptDetector, TransformerPromptService
from tests.test_transformation_continuation import NOW, _session


def test_prompt_explanation_is_durable_and_idempotent(tmp_path: Path):
    engine, session = _session(tmp_path)
    artifact_root = tmp_path / "artifacts" / "run-1"
    session.get(MigrationRunModel, "run-1").artifact_root = str(artifact_root)
    checkpoint = StageCheckpointModel(
        id="checkpoint-1",
        run_id="run-1",
        stage_id="stage-1",
        kind="pre_angular_update",
        sequence=1,
        workspace_alias="STAGE_WORKSPACE_STAGE_1",
        workspace_path=str(tmp_path / "checkpoint"),
        workspace_fingerprint="sha256:checkpoint",
        safe_for_resume=True,
        sealed=False,
        state_version=1,
        created_at=NOW,
    )
    execution = CommandExecutionModel(
        id="execution-angular",
        run_id="run-1",
        stage_id="stage-1",
        executable="npx",
        arguments=["ng", "update"],
        status="running",
        command_id="angular-update-exact",
        requested_at=NOW,
        checkpoint_id=checkpoint.id,
        state_version=1,
        event_sequence=1,
    )
    session.add_all([checkpoint, execution])
    session.flush()
    prompt = TransformerPromptService().capture(
        session,
        execution,
        AngularPromptDetector().detect("Would you like to continue?"),
        now=NOW,
    )
    prompt_id = prompt.id
    session.commit()
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        current = sessions()
        try:
            yield current
            current.commit()
        except Exception:
            current.rollback()
            raise
        finally:
            current.close()

    service = PromptExplanationService(scope=scope, now_provider=lambda: NOW)
    first = service.explain(prompt_id)
    replay = service.explain(prompt_id)

    assert replay == first
    assert first["source"] == "deterministic_fallback"
    with scope() as current:
        invocation = current.get(LlmInvocationModel, f"prompt-explanation-{prompt_id}")
        assert invocation.status == "completed"
        metadata = current.query(ArtifactMetadataModel).one()
        assert Path(artifact_root, metadata.relative_path).exists()
    engine.dispose()
