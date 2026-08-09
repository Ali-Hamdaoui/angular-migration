"""R9 proof: upgrade a genuine Assistant V1 database without losing history."""

import hashlib
import json
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.api.llm_contracts import LlmInvocationResponse
from app.api.routes import assistant as assistant_routes
from app.core.config import Settings
from app.core.database import assert_schema_compatible, expected_heads
from app.domain.contracts import AgentKind
from app.llm_gateway import LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, build_usage_record
from app.main import app
from app.repositories.models import AssistantMessageModel
from app.services.assistant_capabilities import classify_semantic_intent, default_capability_registry
from app.services.assistant_context_service import AssistantContextService

ROOT = Path(__file__).parents[1]
V1_REVISION = "20260723_18"


def _config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _upgrade(database_url: str, revision: str) -> None:
    command.upgrade(_config(database_url), revision)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _seed_v1(database_url: str) -> None:
    """Seed only columns present at V1, using SQL rather than current ORM models."""
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    projection = {"phase": "FEASIBILITY_PLANNING", "stage": "unknown", "status": "WAITING", "state_version": 4}
    usage = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5, "estimated_input_cost": 0.1, "estimated_output_cost": 0.2, "estimated_total_cost": 0.3}

    with create_engine(database_url).begin() as conn:
        conn.execute(text("""
            INSERT INTO migration_runs
            (id, status, run_phase, state_version, source_version_family, target_version_family,
             source_version_detected, source_angular_version, created_at, updated_at, actor)
            VALUES (:id, 'WAITING', 'FEASIBILITY_PLANNING', 4, '18.x', '21.x', '18.2.x', '18.x', :now, :now, 'history-owner')
        """), {"id": "run-r9", "now": now})
        conn.execute(text("""
            INSERT INTO assistant_conversations (id, conversation_id, run_id, created_at, updated_at)
            VALUES (:id, :conversation_id, 'run-r9', :created_at, :updated_at)
        """), [
            {"id": "conversation-a-row", "conversation_id": "conversation-a", "created_at": now, "updated_at": now + timedelta(seconds=4)},
            {"id": "conversation-b-row", "conversation_id": "conversation-b", "created_at": now + timedelta(seconds=1), "updated_at": now + timedelta(seconds=1)},
        ])
        rows = [
            ("a-user-1", "a-user-1", "conversation-a", 1, "user", "Historical question one."),
            ("a-assistant-1", "a-assistant-1", "conversation-a", 2, "assistant", "Historical answer one."),
            ("a-user-2", "a-user-2", "conversation-a", 3, "Historical question two."),
            ("a-assistant-2", "a-assistant-2", "conversation-a", 4, "Historical answer two."),
            ("b-user-1", "b-user-1", "conversation-b", 1, "user", "Other thread question."),
            ("b-assistant-1", "b-assistant-1", "conversation-b", 2, "assistant", "Other thread answer."),
        ]
        for row in rows:
            if len(row) == 6:
                row_id, message_id, conversation_id, order, role, answer = row
            else:
                row_id, message_id, conversation_id, order, answer = row
                role = "user"
            manifest = {"legacy_marker": message_id}
            checksum = "sha256:" + hashlib.sha256(_json(manifest).encode()).hexdigest()
            conn.execute(text("""
                INSERT INTO assistant_messages
                (id, message_id, conversation_id, run_id, message_order, role, input_manifest,
                 input_manifest_checksum, answer, state_version, projection, evidence, proof_label,
                 usage, model_provenance, correlation_id, idempotency_key, status, failure_reason, created_at)
                VALUES (:id, :message_id, :conversation_id, 'run-r9', :message_order, :role, :input_manifest,
                 :checksum, :answer, 4, :projection, :evidence, :proof_label, :usage, :provenance,
                 :correlation_id, :idempotency_key, :status, NULL, :created_at)
            """), {"id": row_id, "message_id": message_id, "conversation_id": conversation_id, "message_order": order,
                   "role": role, "input_manifest": _json(manifest), "checksum": checksum, "answer": answer,
                   "projection": _json(projection), "evidence": "[]", "proof_label": "unknown_or_unavailable",
                   "usage": _json(usage), "provenance": _json({"role": role}), "correlation_id": "corr-" + message_id,
                   "idempotency_key": "legacy-" + message_id, "status": "completed", "created_at": now + timedelta(seconds=order)})
        events = [("event-a-1", "conversation-a", "a-user-1", "ASSISTANT_RESPONSE_STARTED", 1),
                  ("event-a-2", "conversation-a", "a-assistant-1", "ASSISTANT_RESPONSE_COMPLETED", 2),
                  ("event-b-1", "conversation-b", "b-user-1", "ASSISTANT_RESPONSE_STARTED", 3)]
        for event_id, conversation_id, message_id, event_type, sequence in events:
            conn.execute(text("""
                INSERT INTO assistant_lifecycle_events
                (id, run_id, conversation_id, message_id, event_type, sequence, correlation_id,
                 state_version, status, idempotency_key, payload, occurred_at)
                VALUES (:id, 'run-r9', :conversation_id, :message_id, :event_type, :sequence, :correlation_id,
                 4, :status, :idempotency_key, :payload, :occurred_at)
            """), {"id": event_id, "conversation_id": conversation_id, "message_id": message_id,
                   "event_type": event_type, "sequence": sequence, "correlation_id": "corr-" + event_id,
                   "status": event_type.rsplit("_", 1)[-1].lower(), "idempotency_key": "legacy-" + event_id,
                   "payload": _json({"legacy": True}), "occurred_at": now + timedelta(seconds=sequence)})


def _fingerprint(database_url: str) -> dict[str, object]:
    tables = ("assistant_conversations", "assistant_messages", "assistant_lifecycle_events")
    result: dict[str, object] = {}
    engine = create_engine(database_url)
    with engine.connect() as conn:
        for table in tables:
            columns = [column[1] for column in conn.execute(text(f"PRAGMA table_info({table})")) if column[1] not in {
                "request_id", "retry_of_message_id", "semantic_state_version", "operational_event_sequence", "intent", "capability_key", "answer_mode"
            }]
            rows = conn.execute(text(f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid")).mappings().all()
            canonical = [{key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in row.items()} for row in rows]
            result[table] = {"count": len(rows), "ids": [row["id"] for row in canonical], "hash": hashlib.sha256(_json(canonical).encode()).hexdigest()}
    return result


class GovernedFake:
    def complete(self, request):
        question = json.loads(request.prepared_input["serialized_input"])["question"]
        semantic = classify_semantic_intent(question)
        capability = default_capability_registry().get_for_intent(semantic.intent)
        usage = build_usage_record(run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="r9-fake", input_tokens=3, output_tokens=2, input_price_per_million=0.25, output_price_per_million=2.0)
        structured = {"answer": "Current answer appended after V1 history.", "summary": "Current answer.", "intent": semantic.intent, "capability_key": capability.capability_key if capability else "", "proof_label": "authoritative_persisted_fact", "citations": [], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
        return LlmResponse(response_id="r9-response", request_id=request.request_id, run_id=request.run_id, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="r9-fake", status="completed", summary="Current answer.", structured_output=structured, usage=usage, redaction=PromptRedactionResult(redacted_text="safe", redaction_count=0), role=LlmRole.ASSISTANT, prompt_version="r9", schema_version="r9", pricing_version="r9")


def test_r9_additive_v1_upgrade_preserves_history_and_supports_amfa221(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'assistant-v1.db'}"
    _upgrade(database_url, V1_REVISION)
    inspector = inspect(create_engine(database_url))
    assert "request_id" not in {column["name"] for column in inspector.get_columns("assistant_messages")}

    with pytest.raises(RuntimeError, match="Database schema is incompatible"):
        assert_schema_compatible(create_engine(database_url), Settings(database_url=database_url, platform_repository_root=ROOT.parent))

    _seed_v1(database_url)
    before = _fingerprint(database_url)
    assert before["assistant_conversations"]["count"] == 2
    assert before["assistant_messages"]["count"] == 6
    _upgrade(database_url, "heads")
    engine = create_engine(database_url)
    settings = Settings(database_url=database_url, platform_repository_root=ROOT.parent)
    assert_schema_compatible(engine, settings)
    after = _fingerprint(database_url)
    assert after == before
    columns = {column["name"] for column in inspect(engine).get_columns("assistant_messages")}
    assert {"request_id", "retry_of_message_id", "semantic_state_version", "operational_event_sequence", "intent", "capability_key", "answer_mode"}.issubset(columns)
    with engine.connect() as conn:
        defaults = conn.execute(text("SELECT semantic_state_version, operational_event_sequence, intent, capability_key, answer_mode FROM assistant_messages WHERE message_id='a-assistant-1'")).one()
        assert defaults == (1, 0, "unsupported", "", "concise")

    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    service = AssistantContextService(session_scope_factory=scope, gateway=GovernedFake())
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _no_startup_lifespan
    app.dependency_overrides[assistant_routes.get_service] = lambda: service
    app.dependency_overrides[assistant_routes.assistant_authenticated_actor] = lambda: "history-owner"
    try:
        with TestClient(app) as client:
            history_a = client.get("/api/v1/runs/run-r9/assistant/messages?conversation_id=conversation-a")
            history_b = client.get("/api/v1/runs/run-r9/assistant/messages?conversation_id=conversation-b")
            latest = client.get("/api/v1/runs/run-r9/assistant/messages")
            assert history_a.status_code == history_b.status_code == latest.status_code == 200
            assert [item["message_id"] for item in history_a.json()["messages"]] == ["a-user-1", "a-assistant-1", "a-user-2", "a-assistant-2"]
            assert [item["message_id"] for item in history_b.json()["messages"]] == ["b-user-1", "b-assistant-1"]
            assert {item["conversation_id"] for item in latest.json()["messages"]} == {"conversation-a"}
            post = client.post("/api/v1/runs/run-r9/assistant/messages", json={"conversation_id": "conversation-a", "message": "What is the current migration state?", "request_id": "r9-request", "idempotency_key": "r9-idempotency"})
            assert post.status_code == 201, post.text
            new_message_id = post.json()["message_id"]
            combined = client.get("/api/v1/runs/run-r9/assistant/messages?conversation_id=conversation-a")
            assert combined.status_code == 200
            assert [item["message_id"] for item in combined.json()["messages"]][-1] == new_message_id
            assert len(combined.json()["messages"]) == 6
        with engine.connect() as conn:
            current = conn.execute(text("""
                SELECT request_id, retry_of_message_id, semantic_state_version, intent, capability_key, answer_mode
                FROM assistant_messages WHERE message_id = :message_id
            """), {"message_id": new_message_id}).one()
            assert current == ("r9-request", None, 4, "workflow_status", "workflow_status", "concise")
            event_types = conn.execute(text("""
                SELECT event_type FROM assistant_lifecycle_events
                WHERE message_id = :message_id ORDER BY sequence
            """), {"message_id": new_message_id}).scalars().all()
            assert event_types == ["ASSISTANT_RESPONSE_STARTED", "ASSISTANT_CONTEXT_BUILT", "ASSISTANT_RESPONSE_COMPLETED"]
            assert conn.execute(text("SELECT COUNT(*) FROM llm_invocations WHERE run_id='run-r9'" )).scalar_one() == 1
            assert conn.execute(text("SELECT COUNT(*) FROM usage_cost_records WHERE run_id='run-r9'" )).scalar_one() == 1
        restarted = AssistantContextService(session_scope_factory=scope, gateway=GovernedFake())
        restored = restarted.history("run-r9", "conversation-a", actor="history-owner")
        assert [message.message_id for message in restored.messages][:4] == ["a-user-1", "a-assistant-1", "a-user-2", "a-assistant-2"]
        assert restored.messages[-1].request_id == "r9-request"
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        app.dependency_overrides.pop(assistant_routes.assistant_authenticated_actor, None)
        app.router.lifespan_context = original_lifespan

    repeat_before = _fingerprint(database_url)
    _upgrade(database_url, "heads")
    assert _fingerprint(database_url) == repeat_before


@asynccontextmanager
async def _no_startup_lifespan(_app):
    yield


def test_r9_graph_has_v1_parent_and_reaches_all_heads():
    config = _config("sqlite:///:memory:")
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(config)
    v1 = script.get_revision(V1_REVISION)
    assert v1 is not None
    assert v1.down_revision == "20260721_17"
    assert script.get_revision("20260727_19").down_revision == V1_REVISION
    assert set(expected_heads(ROOT)) == {"20260726_27", "20260727_19"}
