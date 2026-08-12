from pathlib import Path

import pytest

from app.domain.transformation import PromptDecisionRequest
from app.repositories.models import (
    CommandExecutionModel,
    StageCheckpointModel,
    StagePromptRequestModel,
)
from app.services.transformation_continuation_service import TransformationContinuationService
from app.services.transformer_prompt_service import (
    AngularPromptDetector,
    TransformerPromptError,
    TransformerPromptService,
)
from tests.test_transformation_continuation import NOW, _create, _session


def test_prompt_detection_is_bounded_and_normalized():
    detected = AngularPromptDetector().detect(
        "noise\nWould you like to migrate the application builder? [y/N]\n"
    )

    assert detected is not None
    assert detected.kind == "boolean"
    assert detected.normalized == "Would you like to migrate the application builder?"
    assert [item["option_id"] for item in detected.options] == ["yes", "no"]


def test_prompt_capture_and_human_decision_are_checksum_and_state_bound(tmp_path: Path):
    engine, session = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), session)
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
    detected = AngularPromptDetector().detect("Do you want to continue? (y/n)")
    prompt = TransformerPromptService().capture(session, execution, detected, now=NOW)
    prompt.status = "waiting_human"
    continuation.status = "waiting_prompt"
    continuation.current_node = "wait_prompt_decision"
    session.flush()
    request = PromptDecisionRequest(
        expected_state_version=continuation.state_version,
        idempotency_key="prompt-answer-1",
        prompt_checksum=prompt.prompt_checksum,
        selected_option_id="no",
        correlation_id="correlation-1",
    )

    decided = TransformerPromptService().decide(
        session, continuation, prompt.id, request, actor="operator", now=NOW
    )
    replay = TransformerPromptService().decide(
        session, continuation, prompt.id, request, actor="operator", now=NOW
    )

    assert replay.id == decided.id
    assert TransformerPromptService.selected_stdin(decided) == "n\n"
    assert continuation.status == "queued"
    assert continuation.current_node == "angular_update"
    changed = request.model_copy(update={"selected_option_id": "yes"})
    with pytest.raises(TransformerPromptError, match="different payload"):
        TransformerPromptService().decide(
            session, continuation, prompt.id, changed, actor="operator", now=NOW
        )
    assert session.query(StagePromptRequestModel).count() == 1
    session.close()
    engine.dispose()
