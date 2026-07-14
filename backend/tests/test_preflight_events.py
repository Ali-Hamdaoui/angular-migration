from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.repositories.models import Base
from app.repositories.preflight_models import PreflightEventModel
from app.services.preflight_events import replay_preflight_events


def test_preflight_events_are_ordered_and_replayable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    now = datetime(2026, 7, 14, tzinfo=UTC)
    with sessions.begin() as session:
        session.add_all([
            PreflightEventModel(id="event-1", preflight_id="preflight-1", event_type="PREFLIGHT_CREATED", payload={}, occurred_at=now, sequence=1),
            PreflightEventModel(id="event-2", preflight_id="preflight-1", event_type="G01_APPROVED", payload={"decision": "approved"}, occurred_at=now, sequence=2),
        ])
    with sessions() as session:
        events = replay_preflight_events(session, "preflight-1")
        replay = replay_preflight_events(session, "preflight-1", last_event_id=1)
    assert [event["sequence"] for event in events] == [1, 2]
    with sessions() as session:
        assert [row.sequence for row in session.query(PreflightEventModel).order_by(PreflightEventModel.sequence)] == [1, 2]
    assert replay[0]["event_type"] == "G01_APPROVED"
