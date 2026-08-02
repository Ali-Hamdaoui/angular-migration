"""Atomic per-run workflow-event sequence allocation (T06).

Per-run event sequences must be allocated atomically so that two
concurrent writers for the same run always receive distinct sequences and
no IntegrityError on uq_workflow_events_run_sequence can surface to callers.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import WorkflowEventType
from app.repositories.migration_run_repository import MigrationRunRepository
from app.repositories.models import Base, MigrationRunModel, WorkflowEventModel
from app.repositories.session import create_database_engine
from app.state import IdempotencyPayloadMismatchError, StateTransitionService


def _database(tmp_path: Path, name: str = "sequencing.db"):
    engine = create_database_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _create_run(session, run_id: str = "run-race", *, status: str = "CREATED") -> None:
    now = datetime.now(UTC)
    session.add(
        MigrationRunModel(
            id=run_id,
            status=status,
            run_phase="FEASIBILITY_PLANNING",
            state_version=1,
            source_version_family="18.x",
            target_version_family="21.x",
            source_version_detected="18.2.x",
            target_version_resolved=None,
            source_angular_version="18.x",
            target_angular_version="21.x",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_two_sessions_appending_for_same_run_get_distinct_sequences_without_integrity_error(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path)
    seed = factory()
    _create_run(seed)
    seed.close()

    first = factory()
    second = factory()
    # Both sessions observe the same latest sequence before appending. Two
    # independent MAX+1 allocators would then both claim sequence 1 and the
    # loser would surface an IntegrityError on commit.
    latest_first = first.scalar(
        select(func.max(WorkflowEventModel.sequence)).where(WorkflowEventModel.run_id == "run-race")
    )
    latest_second = second.scalar(
        select(func.max(WorkflowEventModel.sequence)).where(WorkflowEventModel.run_id == "run-race")
    )
    assert latest_first == latest_second

    first_repository = MigrationRunRepository(first)
    second_repository = MigrationRunRepository(second)
    now = datetime.now(UTC)
    first_event = first_repository.append_event(
        event_id="event-first", run_id="run-race",
        event_type="run_state_changed", occurred_at=now,
    )
    first.commit()
    second_event = second_repository.append_event(
        event_id="event-second", run_id="run-race",
        event_type="stage_state_changed", occurred_at=now,
    )
    second.commit()

    assert {first_event.sequence, second_event.sequence} == {1, 2}
    assert {event.sequence for event in first.query(WorkflowEventModel).all()} == {1, 2}
    first.close()
    second.close()
    engine.dispose()


def test_concurrent_threaded_appends_never_lose_events_or_surface_integrity_errors(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path, "threaded.db")
    seed = factory()
    _create_run(seed)
    seed.close()

    captured: list[tuple[str, int]] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker(tag: str) -> None:
        session = factory()
        repository = MigrationRunRepository(session)
        try:
            barrier.wait()
            for index in range(3):
                event = repository.append_event(
                    event_id=f"event-{tag}-{index}", run_id="run-race",
                    event_type="run_state_changed", occurred_at=datetime.now(UTC),
                )
                session.commit()
                captured.append((tag, event.sequence))
        except Exception as exc:  # pragma: no cover - failure path under test
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    sequences = [sequence for _, sequence in captured]
    assert len(sequences) == 6
    assert len(set(sequences)) == 6
    assert sorted(sequences) == [1, 2, 3, 4, 5, 6]
    engine.dispose()


def test_append_audit_event_same_key_same_payload_replays(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path, "audit.db")
    session = factory()
    _create_run(session)
    service = StateTransitionService(session)
    now = datetime.now(UTC)

    first = service.append_audit_event(
        run_id="run-race", idempotency_key="audit-1",
        event_type=WorkflowEventType.G05_CREATED, actor="tester",
        reason="G05 created", occurred_at=now,
        payload={"package_checksum": "sha256:abc"},
    )
    replay = service.append_audit_event(
        run_id="run-race", idempotency_key="audit-1",
        event_type=WorkflowEventType.G05_CREATED, actor="tester",
        reason="G05 created", occurred_at=now,
        payload={"package_checksum": "sha256:abc"},
    )
    session.commit()

    assert replay.idempotent_replay is True
    assert replay.event_id == first.event_id
    assert session.query(WorkflowEventModel).count() == 1
    session.close()
    engine.dispose()


def test_append_audit_event_same_key_different_payload_conflicts(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path, "audit-conflict.db")
    session = factory()
    _create_run(session)
    service = StateTransitionService(session)
    now = datetime.now(UTC)

    service.append_audit_event(
        run_id="run-race", idempotency_key="audit-2",
        event_type=WorkflowEventType.G05_CREATED, actor="tester",
        reason="G05 created", occurred_at=now,
        payload={"package_checksum": "sha256:abc"},
    )
    session.commit()

    try:
        service.append_audit_event(
            run_id="run-race", idempotency_key="audit-2",
            event_type=WorkflowEventType.G05_CREATED, actor="tester",
            reason="G05 created", occurred_at=now,
            payload={"package_checksum": "sha256:different"},
        )
    except IdempotencyPayloadMismatchError:
        pass
    else:
        raise AssertionError("different payload under the same audit key must conflict")
    session.rollback()

    assert session.query(WorkflowEventModel).count() == 1
    session.close()
    engine.dispose()
