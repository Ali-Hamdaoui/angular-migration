"""Run-scoped, read-only assistant vertical slice for AMFA-221."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select

from app.domain.contracts import (
    AssistantEvidenceDto,
    AssistantHistoryDto,
    AssistantMessageRequestDto,
    AssistantMessageResultDto,
    AssistantUsageDto,
)
from app.llm_gateway import MockLlmGateway
from app.core.config import get_settings
from app.repositories.models import ArtifactMetadataModel, AssistantConversationModel, AssistantLifecycleEventModel, AssistantMessageModel, LlmInvocationModel, MigrationRunModel, UsageCostRecordModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.services.mock_migration_api_service import get_mock_migration_api_service
from app.services.migration_run_service import MigrationRunService

_SECRET = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+")
_PATH = re.compile(r"(?i)([a-z]:\\|/home/|/Users/|/workspace/)[^\s,;]+")
_MAX_HISTORY = 12


class AssistantRequestError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _safe(value: object, limit: int = 500) -> str:
    text = _SECRET.sub("[REDACTED]", str(value or ""))
    text = _PATH.sub("[REDACTED_PATH]", text)
    return text[:limit]


class AssistantContextService:
    """Rebuilds current state before every answer and persists only sanitized output."""

    def __init__(self, *, session_scope_factory=session_scope, gateway: MockLlmGateway | None = None):
        self._scope = session_scope_factory
        self._gateway = gateway or MockLlmGateway()

    def _run(self, run_id: str):
        if run_id.startswith("mock-"):
            return get_mock_migration_api_service().get_state(run_id).model_copy(update={"run_id": run_id, "llm_usage": []})
        with self._scope() as session:
            persisted = session.get(MigrationRunModel, run_id)
            if persisted is not None:
                events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence)))
                artifacts = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id)))
                invocations = list(session.scalars(select(LlmInvocationModel).where(LlmInvocationModel.run_id == run_id)))
                usage_by_invocation = {item.invocation_id: item for item in session.scalars(select(UsageCostRecordModel).where(UsageCostRecordModel.run_id == run_id))}
                usage = [usage_by_invocation[item.id] for item in invocations if item.status == "completed" and item.id in usage_by_invocation]
                return SimpleNamespace(run_id=run_id, status=persisted.status, run_phase=persisted.run_phase, state_version=persisted.state_version, source_angular_version=persisted.source_angular_version, target_angular_version=persisted.target_angular_version, created_at=persisted.created_at, updated_at=persisted.updated_at, stages=[], workflow_events=events, artifacts=[SimpleNamespace(artifact_id=item.id, checksum=item.checksum, relative_path=item.relative_path) for item in artifacts], llm_usage=usage)
        try:
            return MigrationRunService(get_settings()).get_state(run_id)
        except Exception as error:
            if hasattr(error, "code") and hasattr(error, "message"):
                raise AssistantRequestError(str(error.code), str(error.message), 404) from error
            raise

    @staticmethod
    def _recorded_workflow_duration_seconds(run) -> float | None:
        """Calculate stable duration from persisted run and workflow timestamps only."""
        timestamps = [value for value in (getattr(run, "created_at", None),) if isinstance(value, datetime)]
        event_timestamps = [event.occurred_at for event in getattr(run, "workflow_events", []) if isinstance(getattr(event, "occurred_at", None), datetime)]
        timestamps.extend(event_timestamps)
        if not timestamps:
            return None
        status = str(getattr(run, "status", "")).upper()
        terminal_statuses = {"COMPLETED", "CANCELLED", "FAILED", "TIMED_OUT", "WORKER_LOST", "ORPHANED", "CLEANUP_FAILED"}
        if status in terminal_statuses and isinstance(getattr(run, "updated_at", None), datetime):
            event_timestamps.append(run.updated_at)
        end = max(event_timestamps or timestamps)
        return max(0.0, (end - min(timestamps)).total_seconds())

    @staticmethod
    def _projection(run):
        events = sorted(run.workflow_events, key=lambda item: item.sequence)
        phase_key = getattr(run.run_phase, "value", run.run_phase)
        status_value = getattr(run.status, "value", run.status)
        phase = {
            "PREFLIGHT_SNAPSHOT": "Preflight Snapshot",
            "DISCOVERY_BASELINE": "Baseline",
            "FEASIBILITY_PLANNING": "Planning",
            "STAGED_MIGRATION": "Transformation",
            "FINAL_ASSURANCE": "Validation",
            "DELIVERY_REPORTING": "Completion",
        }.get(str(phase_key), "unknown")
        latest = events[-1] if events else None
        event_types = [str(event.event_type) for event in events]
        g02_pending = "G02_CREATED" in event_types and not any(item in event_types for item in ("G02_APPROVED", "G02_REJECTED"))
        integrity_failed = "SOURCE_INTEGRITY_FAILED" in event_types
        failure_reason = next((_safe(event.payload.get("failure_reason") or event.payload.get("error") or event.reason) for event in reversed(events) if event.event_type.endswith("_FAILED") or event.event_type.endswith("_REJECTED")), "unknown")
        blocker = failure_reason if integrity_failed or failure_reason != "unknown" else "none"
        gate = "G02 pending" if g02_pending else next((_safe(event.payload.get("approval_id") or event.payload.get("gate_id") or event.event_type) for event in reversed(events) if event.event_type.startswith("G") and ("_CREATED" in event.event_type or "_APPROVED" in event.event_type or "_REJECTED" in event.event_type)), "unknown")
        waiting_reason = "reviewer decision required for G02" if g02_pending else "unknown"
        stages = list(getattr(run, "stages", []))
        artifacts = list(getattr(run, "artifacts", []))
        completed = [stage.stage_id for stage in stages if str(stage.status).upper() in {"PASSED", "COMPLETED"}]
        if "SOURCE_INTAKE_COMPLETED" in event_types:
            completed.insert(0, "Source intake")
        if ("SNAPSHOT_CREATED" in event_types or "SOURCE_INTEGRITY_VERIFIED" in event_types) and "Source snapshot" not in completed:
            completed.append("Source snapshot")
        if "SOURCE_INTEGRITY_VERIFIED" in event_types and "Source integrity verified" not in completed:
            completed.append("Source integrity verified")
        completed = list(dict.fromkeys(completed))
        current_stage = "G02 Source Integrity Approval" if g02_pending else next((_safe(event.payload.get("stage_name") or event.payload.get("stage_id")) for event in reversed(events) if event.payload.get("stage_name") or event.payload.get("stage_id")), "unknown")
        remaining = ["Runtime validation", "Baseline preparation", "Dependency installation", "Build", "Tests", "Lint", "Baseline qualification"] if str(phase_key) == "PREFLIGHT_SNAPSHOT" else ["Analysis", "Planning", "Transformation", "Validation", "Completion"]
        relevant_ids = []
        for event in events:
            if "G02" in event.event_type or "INTEGRITY" in event.event_type or "SNAPSHOT" in event.event_type:
                ids = event.payload.get("artifact_ids", [])
                relevant_ids.extend(ids if isinstance(ids, list) else [ids])
        relevant_artifacts = [item for item in artifacts if item.artifact_id in relevant_ids or any(marker in str(item.relative_path).lower() for marker in ("g02", "integrity", "snapshot", "workflow_state"))]
        evidence = [{"artifact_id": item.artifact_id, "checksum": item.checksum, "label": item.relative_path} for item in relevant_artifacts[:8]]
        return {
            "application": "Angular migration",
            "run_id": run.run_id,
            "current_angular_version": run.source_angular_version or "unknown",
            "target_angular_version": run.target_angular_version or "unknown",
            "phase": phase,
            "stage": current_stage,
            "step": latest.event_type if latest else "unknown",
            "status": str(status_value),
            "gate": _safe(gate),
            "blocker": blocker,
            "gate_status": "pending" if g02_pending else "unknown",
            "waiting_reason": waiting_reason,
            "failure_reason": failure_reason,
            "next_action": "Record a G02 reviewer decision through the governed cockpit control." if g02_pending else "unknown",
            "completed_phases": completed or ["unknown"],
            "remaining_phases": remaining,
            "state_version": max(1, int(getattr(run, "state_version", 1) or 1), max((int(event.payload.get("next_state_version", 1)) for event in events), default=1)),
            "events": [{"type": event.event_type, "sequence": event.sequence} for event in events[-20:]],
            "evidence": evidence,
            "usage": [{"input_tokens": item.input_tokens, "output_tokens": item.output_tokens, "total_tokens": item.total_tokens, "input_cost_usd": getattr(item, "input_cost_usd", 0.0), "output_cost_usd": getattr(item, "output_cost_usd", 0.0), "cost_usd": getattr(item, "total_cost_usd", getattr(item, "cost_usd", 0.0))} for item in getattr(run, "llm_usage", [])],
            "duration_seconds": AssistantContextService._recorded_workflow_duration_seconds(run),
        }

    @staticmethod
    def _intent(question: str) -> str:
        q = question.lower()
        if any(word in q for word in ("approve", "reject", "apply", "execute", "patch", "modify files", "run command")):
            return "mutation"
        if "where is" in q or "now" in q or "blocked" in q or "next permitted" in q or "current gate" in q or "workflow state" in q:
            return "workflow"
        if "completed" in q:
            return "completed"
        for name, words in {"analysis": ("analysis", "discover"), "planning": ("planning", "propose"), "transformation": ("transformation", "changed"), "validation": ("validation", "passed", "failed")}.items():
            if any(word in q for word in words):
                return name
        if any(word in q for word in ("time", "token", "cost", "consumed", "usage")):
            return "operations"
        return "unsupported"

    def _compose(self, intent: str, projection: dict[str, object]) -> tuple[str, str]:
        if intent == "mutation":
            return "This Assistant is read-only and cannot approve gates, execute commands, apply patches, or change workflow state. Use the governed cockpit control for that action.", "model interpretation"
        if intent == "workflow":
            waiting = projection["waiting_reason"]
            waiting_text = f" It is waiting because {waiting}." if waiting != "unknown" else ""
            blocker_text = "There is no technical blocker." if projection["blocker"] == "none" else f"Blocker: {projection['blocker']}."
            action = projection["next_action"]
            gate = str(projection["gate"])
            gate_status = str(projection["gate_status"])
            gate_text = gate if gate_status == "pending" and gate.lower().endswith(" pending") else f"{gate} ({gate_status})"
            action_text = str(action).rstrip(".")
            return f"The migration is in the {projection['phase']} phase at {projection['stage']}. Current gate: {gate_text}. {blocker_text}{waiting_text} The next permitted action is: {action_text}. Workflow state version: {projection['state_version']}.", "authoritative persisted fact"
        if intent == "completed":
            return f"Completed stages recorded by the current workflow projection: {', '.join(projection['completed_phases'])}. Remaining stages are: {', '.join(projection['remaining_phases'])}.", "authoritative persisted fact"
        if intent in {"analysis", "planning", "transformation", "validation"}:
            matching = [event["type"] for event in projection["events"] if intent.upper() in str(event["type"]).upper() or (intent == "validation" and "BASELINE" in str(event["type"]).upper())]
            evidence = ", ".join(item["artifact_id"] for item in projection["evidence"]) or "unavailable"
            return f"{intent.title()} information currently available from authoritative workflow evidence: events={matching or ['unavailable']}; evidence={evidence}. Facts not present in the persisted projection are unavailable.", "evidence-supported explanation" if matching else "unknown or unavailable"
        if intent == "operations":
            usage = projection["usage"]
            input_tokens = sum(int(item["input_tokens"]) for item in usage)
            output_tokens = sum(int(item["output_tokens"]) for item in usage)
            cost = sum(float(item["cost_usd"]) for item in usage)
            duration = projection["duration_seconds"]
            duration_text = f"Recorded workflow duration: {float(duration):.2f} seconds." if duration is not None else "Recorded workflow duration: unavailable."
            return f"Persisted operational usage: {len(usage)} governed LLM call(s), {input_tokens} input tokens, {output_tokens} output tokens, {input_tokens + output_tokens} total tokens, estimated total cost ${cost:.6f}. {duration_text}", "authoritative persisted fact"
        return "This question is outside the Migration Follow-up Assistant's supported AMFA-221 questions. Ask about current state, completed work, blockers, Analysis, Planning, Transformation, Validation, next permitted action, or operational usage.", "unknown or unavailable"

    def _append_event(self, session, *, run_id: str, conversation_id: str, message_id: str, event_type: str, correlation_id: str, state_version: int, status: str, idempotency_key: str, payload: dict[str, object] | None = None) -> None:
        if session.scalar(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == run_id, AssistantLifecycleEventModel.idempotency_key == idempotency_key, AssistantLifecycleEventModel.event_type == event_type)):
            return
        sequence = int(session.scalar(select(func.max(AssistantLifecycleEventModel.sequence)).where(AssistantLifecycleEventModel.run_id == run_id)) or 0) + 1
        session.add(AssistantLifecycleEventModel(id=uuid4().hex, run_id=run_id, conversation_id=conversation_id, message_id=message_id, event_type=event_type, sequence=sequence, correlation_id=correlation_id, state_version=state_version, status=status, idempotency_key=idempotency_key, payload=payload or {}, occurred_at=datetime.now(UTC)))

    def answer(self, request: AssistantMessageRequestDto, correlation_id: str | None = None) -> AssistantMessageResultDto:
        if not request.run_id:
            raise AssistantRequestError("run_id_required", "A run-scoped assistant request is required.", 422)
        correlation_id = correlation_id or uuid4().hex
        conversation_id = request.conversation_id or uuid4().hex
        message_id = uuid4().hex
        with self._scope() as session:
            prior = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == request.idempotency_key))
            if prior:
                return self._dto(prior)
            history = session.scalars(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id).order_by(AssistantMessageModel.message_order.desc()).limit(_MAX_HISTORY)).all()
        run = self._run(request.run_id)
        projection = self._projection(run)
        stale = request.client_known_state_version is not None and request.client_known_state_version != projection["state_version"]
        manifest = {"question": _safe(request.message, 1000), "projection": projection, "history": [_safe(item.answer, 300) for item in reversed(history)]}
        checksum = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        with self._scope() as session:
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_STARTED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status="started", idempotency_key=request.idempotency_key, payload={"request_id": request.idempotency_key})
        intent = self._intent(request.message)
        answer, proof = self._compose(intent, projection)
        evidence = [AssistantEvidenceDto.model_validate(item) for item in projection["evidence"]]
        input_tokens = sum(int(item["input_tokens"]) for item in projection["usage"])
        output_tokens = sum(int(item["output_tokens"]) for item in projection["usage"])
        input_cost = sum(float(item.get("input_cost_usd", 0.0)) for item in projection["usage"])
        output_cost = sum(float(item.get("output_cost_usd", 0.0)) for item in projection["usage"])
        total_cost = sum(float(item["cost_usd"]) for item in projection["usage"])
        usage = AssistantUsageDto(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens, estimated_input_cost=input_cost, estimated_output_cost=output_cost, estimated_total_cost=total_cost)
        with self._scope() as session:
            prior = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == request.idempotency_key))
            if prior:
                return self._dto(prior)
            count = session.scalar(select(AssistantMessageModel.message_order).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order.desc()).limit(1)) or 0
            now = datetime.now(UTC)
            if not session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)):
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            row = AssistantMessageModel(id=uuid4().hex, message_id=message_id, conversation_id=conversation_id, run_id=request.run_id, message_order=int(count) + 1, role="assistant", input_manifest=manifest, input_manifest_checksum=checksum, answer=answer, state_version=int(projection["state_version"]), projection={"phase": projection["phase"], "stage": projection["stage"], "status": projection["status"], "gate": projection["gate"], "blocker": projection["blocker"], "next_action": projection["next_action"]}, evidence=[item.model_dump(mode="json") for item in evidence], proof_label=proof, usage=usage.model_dump(mode="json"), model_provenance={"role": "deterministic_projection", "deployment": "none", "prompt": "none", "schema": "assistant-response-v1"}, correlation_id=correlation_id, idempotency_key=request.idempotency_key, status="stale" if stale else "completed", created_at=now)
            session.add(row)
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_COMPLETED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status=row.status, idempotency_key=request.idempotency_key, payload={"message_id": message_id})
            return self._dto(row, stale=stale)

    def history(self, run_id: str, conversation_id: str | None = None) -> AssistantHistoryDto:
        current_version = int(self._projection(self._run(run_id))["state_version"])
        with self._scope() as session:
            query = select(AssistantMessageModel).where(AssistantMessageModel.run_id == run_id).order_by(AssistantMessageModel.message_order)
            if conversation_id:
                query = query.where(AssistantMessageModel.conversation_id == conversation_id)
            rows = session.scalars(query).all()
            conversation = conversation_id or (rows[0].conversation_id if rows else uuid4().hex)
            return AssistantHistoryDto(run_id=run_id, conversation_id=conversation, messages=[self._dto(row, stale=row.state_version < current_version) for row in rows])

    @staticmethod
    def _dto(row: AssistantMessageModel, *, stale: bool | None = None) -> AssistantMessageResultDto:
        projection = row.projection
        return AssistantMessageResultDto(message_id=row.message_id, message_order=row.message_order, conversation_id=row.conversation_id, run_id=row.run_id, answer=row.answer, current_phase=str(projection.get("phase", "unknown")), current_stage=str(projection.get("stage", "unknown")), workflow_status=str(projection.get("status", "unknown")), current_gate=str(projection.get("gate", "unknown")), current_blocker=str(projection.get("blocker", "unknown")), next_permitted_action=str(projection.get("next_action", "unknown")), workflow_state_version=row.state_version, stale=stale if stale is not None else row.status == "stale", evidence_references=[AssistantEvidenceDto.model_validate(item) for item in row.evidence], proof_label=row.proof_label, usage=AssistantUsageDto.model_validate(row.usage), response_status=row.status, failure_reason=row.failure_reason)
