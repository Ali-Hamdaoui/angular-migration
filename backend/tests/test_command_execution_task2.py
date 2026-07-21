"""Task 2 regressions for run scoping and immutable execution evidence."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution.worker import CommandLogWriter
from app.domain.contracts import ArtifactType, CommandRequestDto, CommandResultDto, CommandStatus
from app.repositories.models.workflow import CommandExecutionModel
from app.repositories.models.base import Base
from app.services.command_executor_service import CommandExecutorService


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_execution_detail_is_scoped_to_run(db_session):
    now = datetime.now(UTC)
    db_session.add_all([
        CommandExecutionModel(id="exec-owned", run_id="run-a", command_id="node-version", executable="node", arguments=[], status="queued", requested_at=now),
        CommandExecutionModel(id="exec-other", run_id="run-b", command_id="node-version", executable="node", arguments=[], status="queued", requested_at=now),
    ])
    db_session.flush()
    service = CommandExecutorService()

    assert service.get_command_execution(db_session, "run-a", "exec-owned").id == "exec-owned"
    assert service.get_command_execution(db_session, "run-a", "exec-other") is None


def test_command_log_writer_finalizes_empty_stdout_and_stderr(tmp_path):
    store = LocalFilesystemArtifactStore(tmp_path / "artifacts")
    writer = CommandLogWriter(store)
    started = datetime.now(UTC)
    request = CommandRequestDto(
        command_id="node-version", run_id="run-1", executable="node", arguments=["--version"],
        working_directory_alias="run_workspace", runtime_profile_id="source-runtime-profile",
        idempotency_key="execution-1", requested_at=started,
    )
    result = CommandResultDto(
        command_id="node-version", run_id="run-1", status=CommandStatus.SUCCEEDED,
        started_at=started, finished_at=started, exit_code=0,
    )

    evidence = writer.write(request, result, command=("node", "--version"), working_directory=tmp_path, stdout="", stderr="")

    assert evidence.stdout_artifact is not None
    assert evidence.stderr_artifact is not None
    assert store.read_artifact_by_id(evidence.stdout_artifact.ref.artifact_id).ref.checksum == evidence.stdout_artifact.ref.checksum
    assert store.read_artifact_by_id(evidence.stderr_artifact.ref.artifact_id).ref.checksum == evidence.stderr_artifact.ref.checksum
    assert evidence.command_log_artifact.ref.artifact_type == ArtifactType.COMMAND_LOG
