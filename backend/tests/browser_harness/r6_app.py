"""Local-only R6 browser harness around the production Assistant routes."""
from __future__ import annotations

import os
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.authentication import assistant_authenticated_actor
from app.api.routes import assistant as assistant_routes
from app.domain.contracts import AgentKind, WorkflowEventType
from app.llm_gateway import (
    LlmContextSegment,
    LlmRequest,
    LlmResponse,
    LlmRole,
    LlmTaskType,
    LlmUsageRecord,
    PromptRedactionResult,
)
from app.llm_gateway.contracts import LlmUsageRecord as GatewayUsage
from app.repositories.models import (
    AssistantConversationModel,
    AssistantLifecycleEventModel,
    AssistantMessageModel,
    Base,
    MigrationRunModel,
    WorkflowEventModel,
)
from app.services.assistant_context_service import AssistantContextService
from app.services.llm_evidence_application_service import LlmEvidenceApplicationService
from app.services.workflow_projection_service import WorkflowProjectionService
from app.state.transition_service import StateTransitionService, TransitionRequest

ACTOR = "r6-browser-actor"
RUN_ID = "r6-browser-run"
DB_PATH = Path(os.environ.get("R6_DATABASE_PATH", Path(os.environ.get("TEMP", ".")) / "r6-browser.sqlite3"))
ARTIFACT_ROOT = DB_PATH.parent / "r6-browser-artifacts"
engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class ControlledGateway:
    def __init__(self):
        self.mode = "success"
        self.started = False
        self.released = False
        self.calls = 0
        self._release = threading.Event()

    def reset(self):
        self.mode = "success"
        self.started = False
        self.released = False
        self.calls = 0
        self._release.clear()

    def release(self):
        self.released = True
        self._release.set()

    def complete(self, request: LlmRequest, prior_usage=None) -> LlmResponse:
        self.calls += 1
        self.started = True
        if self.mode == "delayed_success":
            self._release.wait(timeout=60)
        if self.mode == "failure":
            from app.llm_gateway.azure_gateway import AzureGatewayError, LlmFailureCode
            raise AzureGatewayError(LlmFailureCode.PROVIDER, "controlled provider failure")
        now = datetime.now(UTC)
        usage = GatewayUsage(usage_id=f"r6-usage-{self.calls}", run_id=request.run_id, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="r6-controlled", input_tokens=8, output_tokens=12, total_tokens=20, input_price_per_million=0, output_price_per_million=0, input_cost_usd=0, output_cost_usd=0, total_cost_usd=0, created_at=now)
        intent = "next_steps" if "next permitted action" in (request.prepared_input or {}).get("serialized_input", "").lower() else "workflow_status"
        capability = "next_steps" if intent == "next_steps" else "workflow_status"
        structured = {"answer": "Controlled Assistant answer.", "summary": "Controlled R6 answer.", "intent": intent, "capability_key": capability, "proof_label": "authoritative_persisted_fact", "citations": [], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}
        return LlmResponse(response_id=f"r6-response-{self.calls}", request_id=request.request_id, run_id=request.run_id, agent_kind=request.agent_kind, task_type=request.task_type, model_deployment_alias="r6-controlled", status="completed", summary="controlled", structured_output=structured, usage=usage, redaction=PromptRedactionResult(redacted_text="controlled", redaction_count=0), role=LlmRole.ASSISTANT, prompt_version="assistant-response-v1", schema_version="assistant-response-v1", pricing_version="r6-test")


gateway = ControlledGateway()
stream_faults = {"disconnect": False, "duplicate": False, "skip": False}


class R8StreamFaultMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if not request.url.path.endswith("/assistant/events"):
            return response
        source = response.body_iterator

        async def controlled_body():
            async for chunk in source:
                text = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
                data_event = "event: " in text and "data: " in text
                if data_event and stream_faults["skip"]:
                    stream_faults["skip"] = False
                    continue
                yield chunk
                if data_event and stream_faults["duplicate"]:
                    stream_faults["duplicate"] = False
                    yield chunk
                if stream_faults["disconnect"]:
                    stream_faults["disconnect"] = False
                    return

        response.body_iterator = controlled_body()
        return response


class GatewayModeRequest(BaseModel):
    mode: str


def get_service() -> AssistantContextService:
    return AssistantContextService(session_scope_factory=scope, invocation_service=LlmEvidenceApplicationService(session_scope_factory=scope, gateway=gateway))


def fixed_actor():
    return ACTOR


app = FastAPI(title="R6 browser harness")
app.add_middleware(R8StreamFaultMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3312"], allow_methods=["*"], allow_headers=["*"], allow_credentials=False)
app.dependency_overrides[assistant_routes.get_service] = get_service
app.dependency_overrides[assistant_routes.assistant_authenticated_actor] = fixed_actor
# R8 browser proof keeps the real durable route but injects short test-only
# liveness values. These controls are not mounted in the production app.
assistant_routes.ASSISTANT_SSE_POLL_INTERVAL_SECONDS = 0.05
assistant_routes.ASSISTANT_SSE_HEARTBEAT_INTERVAL_SECONDS = 1.0
# The production event route imports its session factory directly; redirect
# that test-only seam as well, without changing the production application.
assistant_routes.session_scope = scope
app.include_router(assistant_routes.router, prefix="/api/v1")


@app.get("/api/v1/runs/{run_id}/state")
def run_state(run_id: str):
    from app.core.config import get_settings
    from app.services.migration_run_service import MigrationRunService
    return MigrationRunService(settings=get_settings(), session_scope_factory=scope).get_state(run_id)

control = APIRouter(prefix="/__test__/r6")


@control.post("/reset")
def reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    gateway.reset()
    for key in stream_faults:
        stream_faults[key] = False
    return {"status": "reset"}


@control.post("/seed")
def seed(kind: str = "latest"):
    now = datetime.now(UTC)
    with scope() as session:
        if session.get(MigrationRunModel, RUN_ID) is None:
            session.add(MigrationRunModel(id=RUN_ID, status="RUNNING", run_phase="DISCOVERY_BASELINE", phase_status="running", approval_status="not_required", repair_status="not_required", state_version=1, source_path="r6-source", target_output_path="r6-target", actor=ACTOR, created_at=now, updated_at=now, graph_thread_id="r6-thread", artifact_root=str(ARTIFACT_ROOT)))
        ids = {"latest": "r6-conversation-latest", "a": "r6-conversation-a", "b": "r6-conversation-b", "next": "r6-conversation-next"}
        selected = [ids.get(kind, ids["latest"])] if kind != "both" else [ids["a"], ids["b"]]
        for conversation_index, conversation_id in enumerate(selected):
            if session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == RUN_ID, AssistantConversationModel.conversation_id == conversation_id)):
                continue
            conversation_now = now + timedelta(microseconds=conversation_index)
            session.add(AssistantConversationModel(id=uuid.uuid4().hex, run_id=RUN_ID, conversation_id=conversation_id, created_at=conversation_now, updated_at=conversation_now))
            projection = WorkflowProjectionService().build(session, RUN_ID).model_dump(mode="json") if session.get(MigrationRunModel, RUN_ID) else {}
            if kind == "next":
                proposals = list(projection.get("next_step_proposals") or [])
                proposals.insert(0, {"action_key": "review_g02", "label": "Review migration guidance", "reason": "Human approval is required before the governed review step.", "target_route": f"/api/v1/runs/{RUN_ID}/approvals/G02", "requires_human_approval": True, "executable_by_assistant": False})
                proposals.append({"action_key": "route_less_recommendation", "label": "Migration guidance recommendation", "reason": "This recommendation has no governed destination yet.", "target_route": None, "requires_human_approval": False, "executable_by_assistant": False})
                projection["next_step_proposals"] = proposals
            marker = conversation_id.removeprefix("r6-conversation-")
            for order, role, text in ((1, "user", f"seed-{marker}-user"), (2, "assistant", f"seed-{marker}-answer")):
                session.add(AssistantMessageModel(id=uuid.uuid4().hex, message_id=f"r6-{marker}-{order}", conversation_id=conversation_id, run_id=RUN_ID, message_order=order, role=role, input_manifest={}, input_manifest_checksum="seed", answer=text, state_version=1, semantic_state_version=1, operational_event_sequence=0, projection=projection, evidence=[], proof_label="authoritative_persisted_fact", usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_input_cost": 0, "estimated_output_cost": 0, "estimated_total_cost": 0}, model_provenance={"role": role}, correlation_id=f"r6-correlation-{marker}", idempotency_key=f"r6-seed-{marker}-{order}", status="completed", failure_reason=None, created_at=now, intent="workflow_status", capability_key="assistant.workflow_status", answer_mode="concise"))
    return {"run_id": RUN_ID, "conversation_ids": selected}


@control.post("/gateway/mode")
def set_mode(request: GatewayModeRequest):
    mode = request.mode
    if mode not in {"success", "delayed_success", "failure"}:
        return {"status": "invalid"}
    gateway.mode = mode
    gateway.started = False
    gateway.released = False
    gateway._release.clear()
    return {"mode": mode}


@control.post("/gateway/release")
def release():
    gateway.release()
    return {"released": True}


@control.get("/metrics")
def metrics():
    return {"provider_call_count": gateway.calls, "provider_started": gateway.started, "provider_released": gateway.released, "current_mode": gateway.mode}


@control.get("/events")
def lifecycle_events():
    with scope() as session:
        rows = session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == RUN_ID).order_by(AssistantLifecycleEventModel.sequence)).all()
        return {"events": [{"sequence": row.sequence, "event_type": row.event_type} for row in rows]}


@control.post("/stream/fault")
def stream_fault(kind: str):
    if kind not in stream_faults:
        return {"status": "invalid"}
    stream_faults[kind] = True
    return {"status": "armed", "kind": kind}


@control.post("/semantic-transition")
def semantic_transition():
    with scope() as session:
        run = session.get(MigrationRunModel, RUN_ID)
        previous = run.state_version
        result = StateTransitionService(session).apply_transition(TransitionRequest(run_id=RUN_ID, expected_state_version=previous, idempotency_key=f"r6-semantic-transition-{previous}", event_type=WorkflowEventType.RUN_STATE_CHANGED, actor=ACTOR, reason="test-only governed semantic transition", occurred_at=datetime.now(UTC), payload={"test_only_semantic_transition": True}))
    return {"previous_semantic_version": result.previous_state_version, "new_semantic_version": result.next_state_version, "transition_key": result.idempotency_key}


app.include_router(control)
