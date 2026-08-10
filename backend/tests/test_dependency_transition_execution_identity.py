from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.dependency_transition_runner as runner_module
from app.domain.command import NPM_DEPENDENCY_INSTALL_RENDERER, NPM_DEPENDENCY_UNINSTALL_RENDERER
from app.repositories.models import CommandExecutionModel
from app.repositories.models.base import Base
from app.services.dependency_transition_runner import DependencyTransitionError, DependencyTransitionRunner


NOW = datetime(2026, 8, 10, tzinfo=UTC)
PACKAGE = "blocking-package"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    value = sessionmaker(bind=engine)()
    Base.metadata.create_all(engine)
    yield value
    value.close()
    engine.dispose()


def _continuation():
    return SimpleNamespace(run_id="run-1", current_stage_id="stage-1")


def _context(tmp_path):
    return {
        "run": SimpleNamespace(id="run-1"),
        "attempt": SimpleNamespace(id="repair-current"),
        "binding": SimpleNamespace(workspace_path=str(tmp_path)),
        "workspace": tmp_path,
        "intent": {
            "blocking_package": PACKAGE,
            "installed_version": "1.0.0",
            "peer_ranges": {"peer-package": "^1.0.0"},
            "evidence_diagnosis": {"source": "angular_update_peer_conflict"},
            "transition_targets": [{"package": PACKAGE, "exact_version": "2.0.0"}],
        },
    }


def _execution(execution_id, key, command_id, arguments, status="succeeded", exit_code=0):
    return CommandExecutionModel(
        id=execution_id,
        run_id="run-1",
        stage_id="stage-1",
        idempotency_key=key,
        executable="npm",
        arguments=arguments,
        status=status,
        requested_at=NOW,
        finished_at=NOW if status == "succeeded" else None,
        exit_code=exit_code,
        command_id=command_id,
    )


def test_new_transition_ignores_historical_commands_and_queues_its_own(session, tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(
        '{"devDependencies":{"blocking-package":"^1.0.0"}}', encoding="utf-8"
    )
    session.add_all([
        _execution(
            "exec-old-uninstall",
            "repair-old:transition:uninstall",
            "npm-dependency-uninstall",
            list(NPM_DEPENDENCY_UNINSTALL_RENDERER.render_arguments({"package": PACKAGE})),
        ),
        _execution(
            "exec-old-install",
            "repair-old:transition:install:attempt-1",
            "npm-dependency-install",
            list(NPM_DEPENDENCY_INSTALL_RENDERER.render_arguments(
                {"package": PACKAGE, "target_version": "2.0.0"}
            )),
        ),
    ])
    session.commit()
    runner = DependencyTransitionRunner(stage_service=MagicMock())
    runner._queue_transition_command = MagicMock(return_value="queued")
    monkeypatch.setattr(
        runner_module, "verify_dependency_transition_evidence_for_source", MagicMock()
    )

    assert runner._phase_uninstall(session, _continuation(), _context(tmp_path)) == "queued"
    assert runner._queue_transition_command.call_args.args[4] == "repair-current:transition:uninstall"
    runner._queue_transition_command.reset_mock()
    assert runner._phase_install(session, _continuation(), _context(tmp_path)) == "queued"
    assert runner._queue_transition_command.call_args.args[4] == "repair-current:transition:install:attempt-1"


@pytest.mark.parametrize("status", ["queued", "pending", "running"])
def test_same_transition_replay_waits_on_its_active_uninstall_without_duplicate(session, tmp_path, status):
    current = _execution(
        f"exec-{status}",
        "repair-current:transition:uninstall",
        "npm-dependency-uninstall",
        list(NPM_DEPENDENCY_UNINSTALL_RENDERER.render_arguments({"package": PACKAGE})),
        status,
        None,
    )
    session.add(current)
    session.commit()
    stage = MagicMock()
    runner = DependencyTransitionRunner(stage_service=stage)
    runner._queue_transition_command = MagicMock()

    assert runner._phase_uninstall(session, _continuation(), _context(tmp_path)) == "waiting"
    stage._wait_for_command.assert_called_once_with(session, _continuation(), current.id)
    runner._queue_transition_command.assert_not_called()


def test_terminal_current_uninstall_proceeds_to_post_state_verification(session, tmp_path):
    current = _execution(
        "exec-current",
        "repair-current:transition:uninstall",
        "npm-dependency-uninstall",
        list(NPM_DEPENDENCY_UNINSTALL_RENDERER.render_arguments({"package": PACKAGE})),
    )
    session.add(current)
    session.commit()
    runner = DependencyTransitionRunner(stage_service=MagicMock())
    runner._verify_uninstall = MagicMock()

    assert runner._phase_uninstall(session, _continuation(), _context(tmp_path)) == "continue"
    runner._verify_uninstall.assert_called_once_with(session, _continuation(), _context(tmp_path), current)


def test_uninstall_post_state_verification_still_fails_closed(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"devDependencies":{"blocking-package":"^1.0.0"}}', encoding="utf-8"
    )
    runner = DependencyTransitionRunner(stage_service=MagicMock())

    with pytest.raises(DependencyTransitionError) as raised:
        runner._verify_uninstall(MagicMock(), _continuation(), _context(tmp_path), SimpleNamespace(id="exec"))

    assert raised.value.code == "DEPENDENCY_TRANSITION_UNINSTALL_VERIFICATION_FAILED"
