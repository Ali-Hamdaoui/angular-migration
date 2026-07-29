"""Run-scoped, read-only assistant vertical slice for AMFA-221."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select

from app.api.authentication import authorize_run, require_authenticated_actor
from app.artifact_store.local_store import LocalFilesystemArtifactStore
from app.core.config import get_settings
from app.domain.contracts import (
    AgentKind,
    AssistantEvidenceDto,
    AssistantHistoryDto,
    AssistantMessageRequestDto,
    AssistantMessageResultDto,
    AssistantOperationalStatisticsDto,
    AssistantUsageDto,
)
from app.llm_gateway import LlmContextSegment
from app.repositories.models import (
    ArtifactMetadataModel,
    AssistantConversationModel,
    AssistantLifecycleEventModel,
    AssistantMessageModel,
    ExecutionProfileModel,
    G02ApprovalModel,
    LlmInvocationModel,
    MigrationRunModel,
    SourceSnapshotModel,
    UsageCostRecordModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.assistant_capabilities import (
    classify_semantic_intent,
    default_capability_registry,
    is_mutation_request,
)
from app.services.assistant_context_budget import ContextBudgetExceeded, prepare_assistant_request
from app.services.assistant_evidence_retrieval_service import AssistantEvidenceRetrievalService
from app.services.llm_evidence_application_service import AssistantInvocationRequest, LlmEvidenceApplicationService, build_assistant_response_contract
from app.llm_gateway.azure_gateway import _azure_strict_schema
from app.services.migration_run_service import MigrationRunService
from app.services.mock_migration_api_service import get_mock_migration_api_service
from app.services.workflow_projection_service import WorkflowProjectionService

_SECRET = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+")
_PATH = re.compile(r"(?i)([a-z]:\\|/home/|/Users/|/workspace/)[^\s,;]+")
_MAX_HISTORY = 12


class AssistantRequestError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409, *, correlation_id: str | None = None, details: dict[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.correlation_id = correlation_id
        self.details = details or {}


def _safe(value: object, limit: int = 500) -> str:
    text = _SECRET.sub("[REDACTED]", str(value or ""))
    text = _PATH.sub("[REDACTED_PATH]", text)
    return text[:limit]


def _safe_question(value: object) -> str:
    """Sanitize the complete question without semantic truncation."""
    text = _SECRET.sub("[REDACTED]", str(value or ""))
    return _PATH.sub("[REDACTED_PATH]", text)


class AssistantContextService:
    """Rebuilds current state before every answer and persists only sanitized output."""

    def __init__(self, *, session_scope_factory=session_scope, gateway=None, invocation_service=None):
        self._scope = session_scope_factory
        # A gateway is an explicit test/provider seam.  Normal API construction
        # must use the production application service, which resolves the
        # configured governed gateway lazily and fails explicitly when absent.
        self._invocations = invocation_service or LlmEvidenceApplicationService(session_scope_factory=session_scope_factory, gateway=gateway)
        self._capabilities = default_capability_registry()
        self._evidence_retrieval = AssistantEvidenceRetrievalService()

    def authorize(self, run_id: str, actor: str) -> None:
        actor = require_authenticated_actor(actor)
        if run_id.startswith("mock-"):
            return
        with self._scope() as session:
            authorize_run(session, run_id, actor, forbidden_code="assistant_run_forbidden")

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
                return SimpleNamespace(run_id=run_id, status=persisted.status, run_phase=persisted.run_phase, state_version=persisted.state_version, source_angular_version=persisted.source_angular_version, target_angular_version=persisted.target_angular_version, created_at=persisted.created_at, updated_at=persisted.updated_at, stages=[], workflow_events=events, artifacts=[SimpleNamespace(artifact_id=item.id, checksum=item.checksum, relative_path=item.relative_path) for item in artifacts], llm_usage=usage, assistant_projection=WorkflowProjectionService().build(session, run_id))
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
        shared = getattr(run, "assistant_projection", None)
        if shared is not None:
            data = shared.model_dump(mode="json") if hasattr(shared, "model_dump") else shared
            def value(name: str, fallback: str = "unknown") -> str:
                item = data.get(name) or {}
                return str(item.get("value") if item.get("availability") == "known" else fallback)
            stats = data.get("operational_statistics") or {}
            evidence = data.get("evidence_references") or []
            return {
                "application": value("application_name"), "run_id": data.get("run_id", getattr(run, "run_id", "unknown")),
                "current_angular_version": value("current_angular_version"), "target_angular_version": value("target_angular_version"),
                "phase": value("phase"), "stage": value("stage"), "step": value("step"), "status": value("status"),
                "gate": value("gate"), "gate_status": "pending" if value("gate").lower().endswith("pending") else value("gate"), "blocker": value("blocker"), "waiting_reason": value("waiting_reason"),
                "failure_reason": value("failure_reason"), "next_action": value("next_permitted_action"),
                "completed_phases": data.get("completed_work", []), "remaining_phases": data.get("remaining_work", []),
                "state_version": int(data.get("semantic_state_version", data.get("workflow_state_version", 1))), "events": [],
                "next_step_proposals": data.get("next_step_proposals", []), "failure_classification": value("failure_classification"),
                "evidence": [{"artifact_id": item["artifact_id"], "checksum": item["checksum"], "label": item["label"]} for item in evidence],
                "usage": [{"input_tokens": stats["input_tokens"], "output_tokens": stats["output_tokens"], "total_tokens": stats["total_tokens"], "input_cost_usd": stats["input_cost_usd"], "output_cost_usd": stats["output_cost_usd"], "cost_usd": stats["total_cost_usd"]}] if stats.get("input_tokens") is not None else [],
                "duration_seconds": stats.get("recorded_workflow_duration_seconds"),
                "operational_statistics": stats, "operational_event_sequence": data.get("operational_event_sequence", 0),
            }
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
        intent = {
            "workflow_status": "workflow", "blocker_or_failure": "validation",
            "completed_work": "completed", "usage_and_cost": "operations",
            "analysis_explanation": "analysis", "planning_explanation": "planning",
            "transformation_explanation": "transformation", "validation_explanation": "validation",
            "next_steps": "workflow", "remaining_work": "completed", "comparison": "workflow",
            "evidence_question": "analysis",
        }.get(intent, intent)
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
            if not usage:
                duration = projection.get("duration_seconds")
                duration_text = f" Recorded workflow duration: {float(duration):.2f} seconds." if duration is not None else ""
                return f"Persisted LLM token and cost statistics are unavailable because no authoritative usage records exist.{duration_text}", "unknown or unavailable"
            input_tokens = sum(int(item["input_tokens"]) for item in usage)
            output_tokens = sum(int(item["output_tokens"]) for item in usage)
            cost = sum(float(item["cost_usd"]) for item in usage)
            duration = projection["duration_seconds"]
            duration_text = f"Recorded workflow duration: {float(duration):.2f} seconds." if duration is not None else "Recorded workflow duration: unavailable."
            return f"Persisted operational usage: {len(usage)} governed LLM call(s), {input_tokens} input tokens, {output_tokens} output tokens, {input_tokens + output_tokens} total tokens, estimated total cost ${cost:.6f}. {duration_text}", "authoritative persisted fact"
        return "This question is outside the Migration Follow-up Assistant's supported AMFA-221 questions. Ask about current state, completed work, blockers, Analysis, Planning, Transformation, Validation, next permitted action, or operational usage.", "unknown or unavailable"

    @staticmethod
    def _authoritative_workflow_answer(projection: dict[str, object]) -> str:
        completed = projection.get("completed_work") or projection.get("completed") or projection.get("completed_phases") or []
        if not isinstance(completed, list):
            completed = [completed]
        blocker = str(projection.get("blocker") or "NO_COMPATIBLE_RUNTIME_PROFILE")
        action = str(projection.get("next_action") or "Install or expose an approved paired Node/npm/npx runtime. Retry runtime-profile resolution.")
        return (
            f"Status: {projection.get('status', 'FAILED')}. Blocker: {blocker}. "
            f"Completed: {', '.join(str(item) for item in completed)}. "
            "Runtime result: execution-profile resolution blocked. "
            f"Next permitted action: {action}"
        )

    def _append_event(self, session, *, run_id: str, conversation_id: str, message_id: str, event_type: str, correlation_id: str, state_version: int, status: str, idempotency_key: str, payload: dict[str, object] | None = None) -> None:
        if session.scalar(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == run_id, AssistantLifecycleEventModel.idempotency_key == idempotency_key, AssistantLifecycleEventModel.event_type == event_type)):
            return
        sequence = int(session.scalar(select(func.max(AssistantLifecycleEventModel.sequence)).where(AssistantLifecycleEventModel.run_id == run_id)) or 0) + 1
        session.add(AssistantLifecycleEventModel(id=uuid4().hex, run_id=run_id, conversation_id=conversation_id, message_id=message_id, event_type=event_type, sequence=sequence, correlation_id=correlation_id, state_version=state_version, status=status, idempotency_key=idempotency_key, payload=payload or {}, occurred_at=datetime.now(UTC)))

    @staticmethod
    def _request_checksum(request: AssistantMessageRequestDto) -> str:
        payload = {
            "run_id": request.run_id,
            "message": _safe_question(request.message),
            "conversation_id": request.conversation_id,
            "answer_mode": request.answer_mode,
            "retry_of_message_id": request.retry_of_message_id,
            "client_known_state_version": request.client_known_state_version,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _validate_retry_target(session, request: AssistantMessageRequestDto, *, conversation_id: str | None, correlation_id: str) -> tuple[str, str]:
        target = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.message_id == request.retry_of_message_id))
        if target is None:
            raise AssistantRequestError("assistant_retry_target_not_found", "The requested Assistant failure could not be found.", 404, correlation_id=correlation_id)
        if target.role != "assistant" or target.status != "failed":
            raise AssistantRequestError("assistant_retry_target_invalid", "Only a failed Assistant message can be retried.", 422, correlation_id=correlation_id)
        if conversation_id is not None and target.conversation_id != conversation_id:
            raise AssistantRequestError("assistant_retry_target_invalid", "The failed Assistant message is not in this conversation.", 422, correlation_id=correlation_id)
        paired = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.conversation_id == target.conversation_id, AssistantMessageModel.role == "user", AssistantMessageModel.message_order < target.message_order).order_by(AssistantMessageModel.message_order.desc()).limit(1))
        if paired is None or not paired.answer:
            raise AssistantRequestError("assistant_retry_target_invalid", "The failed Assistant message has no recoverable original request.", 422, correlation_id=correlation_id)
        if _safe_question(request.message) != paired.answer or request.answer_mode != target.answer_mode:
            raise AssistantRequestError("assistant_retry_target_invalid", "Retry must repeat the original question and answer mode.", 422, correlation_id=correlation_id)
        return target.conversation_id, paired.answer

    @staticmethod
    def _message_projection(projection: dict[str, object]) -> dict[str, object]:
        return {"phase": projection["phase"], "stage": projection["stage"], "status": projection["status"], "gate": projection["gate"], "blocker": projection["blocker"], "next_action": projection["next_action"], "next_step_proposals": projection.get("next_step_proposals", []), "failure_classification": projection.get("failure_classification", "unavailable"), "operational_statistics": projection.get("operational_statistics", {})}

    def _persist_user_message(self, session, request, *, conversation_id, correlation_id, projection, manifest, checksum, message_order, now, status="pending"):
        session.add(AssistantMessageModel(
            id=uuid4().hex, message_id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id,
            message_order=message_order, role="user", input_manifest=manifest, input_manifest_checksum=checksum,
            answer=_safe_question(request.message), state_version=int(projection["state_version"]), semantic_state_version=int(projection["state_version"]), operational_event_sequence=int(projection.get("operational_statistics", {}).get("event_sequence", 0) or 0),
            projection=self._message_projection(projection), evidence=[], proof_label="user request",
            usage=AssistantUsageDto(input_tokens=0, output_tokens=0, total_tokens=0, estimated_input_cost=0, estimated_output_cost=0, estimated_total_cost=0).model_dump(mode="json"),
            model_provenance={"role": "user"}, correlation_id=correlation_id,
            idempotency_key=hashlib.sha256(("user:" + request.idempotency_key).encode()).hexdigest(),
            request_id=request.request_id, retry_of_message_id=request.retry_of_message_id,
            status=status, failure_reason=None, created_at=now,
        ))

    def _persist_failed_result(self, request, *, conversation_id, message_id, correlation_id, projection, manifest, checksum, reason, code, intent="unsupported", capability_key="", model=None):
        with self._scope() as session:
            prior = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == request.idempotency_key))
            if prior:
                return self._dto(prior, session=session)
            count = session.scalar(select(AssistantMessageModel.message_order).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order.desc()).limit(1)) or 0
            now = datetime.now(UTC)
            if not session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)):
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            user_key = hashlib.sha256(("user:" + request.idempotency_key).encode()).hexdigest()
            user = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == user_key))
            if user is None:
                self._persist_user_message(session, request, conversation_id=conversation_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, message_order=int(count) + 1, now=now, status="completed")
            else:
                user.status = "completed"
            row = AssistantMessageModel(id=uuid4().hex, message_id=message_id, conversation_id=conversation_id, run_id=request.run_id, message_order=int(count) + 2, role="assistant", input_manifest=manifest, input_manifest_checksum=checksum, answer="The Assistant request failed before producing a completed answer.", state_version=int(projection["state_version"]), semantic_state_version=int(projection["state_version"]), operational_event_sequence=int(projection.get("operational_statistics", {}).get("event_sequence", 0) or 0), projection=self._message_projection(projection), evidence=[], proof_label="unknown_or_unavailable", usage=AssistantUsageDto(input_tokens=0, output_tokens=0, total_tokens=0, estimated_input_cost=0, estimated_output_cost=0, estimated_total_cost=0).model_dump(mode="json"), model_provenance={"role": "assistant", "failure_code": code, "deployment": model, "assistant_v11": {"schema_version": "assistant-response-v1", "resolved": True}}, correlation_id=correlation_id, idempotency_key=request.idempotency_key, request_id=request.request_id, retry_of_message_id=request.retry_of_message_id, intent=intent, capability_key=capability_key, answer_mode=request.answer_mode, status="failed", failure_reason=reason, created_at=now)
            session.add(row)
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_FAILED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status="failed", idempotency_key=request.idempotency_key, payload={"failure_code": code})
            return self._dto(row, session=session)

    @classmethod
    def _validated_citations(cls, citations: object, selected_refs: list[dict[str, object]], *, proof_label: str):
        """Validate only against the exact excerpts supplied in this call."""
        if not isinstance(citations, list):
            return None
        by_id = {str(item["excerpt_id"]): item for item in selected_refs}
        validated: list[dict[str, object]] = []
        seen: set[str] = set()
        for citation in citations:
            if not isinstance(citation, dict):
                return None
            excerpt_id = citation.get("excerpt_id")
            selected = by_id.get(str(excerpt_id)) if excerpt_id else None
            if selected is None:
                return None
            exact = {
                "excerpt_id": selected["excerpt_id"],
                "artifact_id": selected["artifact_id"],
                "checksum_sha256": selected["checksum_sha256"],
                "stage_key": selected["stage_key"],
                "locator": selected["locator"],
                "proof_label": selected["proof_label"],
            }
            if any(citation.get(key) != value for key, value in exact.items()):
                return None
            if exact["proof_label"] != "approved_evidence_supported" or proof_label not in {"approved_evidence_supported", "model_interpretation"}:
                return None
            if str(excerpt_id) not in seen:
                validated.append(exact)
                seen.add(str(excerpt_id))
        if proof_label == "approved_evidence_supported" and not validated:
            return None
        return validated

    @classmethod
    def _validate_citations(cls, citations: object, selected_refs: list[dict[str, object]], *, proof_label: str) -> bool:
        return cls._validated_citations(citations, selected_refs, proof_label=proof_label) is not None

    def answer(self, request: AssistantMessageRequestDto, correlation_id: str | None = None, actor: str | None = None) -> AssistantMessageResultDto:
        if not request.run_id:
            raise AssistantRequestError("run_id_required", "A run-scoped assistant request is required.", 422)
        self.authorize(request.run_id, actor or "")
        request_id = request.request_id or request.idempotency_key or uuid4().hex
        request = request.model_copy(update={"request_id": request_id, "idempotency_key": request.idempotency_key or request_id})
        correlation_id = correlation_id or uuid4().hex
        message_id = uuid4().hex
        with self._scope() as session:
            prior = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == request.idempotency_key))
            if prior:
                if request.conversation_id is not None and request.conversation_id != prior.conversation_id:
                    raise AssistantRequestError("assistant_idempotency_conflict", "The idempotency key was used with a different payload.", 409, correlation_id=correlation_id)
                request_checksum = self._request_checksum(request.model_copy(update={"conversation_id": prior.conversation_id}))
                if prior.input_manifest_checksum != request_checksum:
                    raise AssistantRequestError("assistant_idempotency_conflict", "The idempotency key was used with a different payload.", 409, correlation_id=correlation_id)
                return self._dto(prior, session=session)
            user_key = hashlib.sha256(("user:" + request.idempotency_key).encode()).hexdigest()
            prior_user = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == user_key))
            if prior_user:
                request_checksum = self._request_checksum(request.model_copy(update={"conversation_id": prior_user.conversation_id}))
                if prior_user.input_manifest_checksum != request_checksum:
                    raise AssistantRequestError("assistant_idempotency_conflict", "The idempotency key was used with a different payload.", 409, correlation_id=correlation_id)
                raise AssistantRequestError("assistant_request_in_progress", "The original Assistant request is still in progress; reuse its transport identifiers.", 409, correlation_id=correlation_id, details={"conversation_id": prior_user.conversation_id, "request_id": prior_user.request_id})
            if request.retry_of_message_id:
                conversation_id, _ = self._validate_retry_target(session, request, conversation_id=request.conversation_id, correlation_id=correlation_id)
            elif request.conversation_id:
                selected_conversation = request.conversation_id
                conversation_id = selected_conversation
            else:
                selected_conversation = session.scalar(select(AssistantConversationModel.conversation_id).where(AssistantConversationModel.run_id == request.run_id).order_by(AssistantConversationModel.updated_at.desc()).limit(1))
                conversation_id = selected_conversation or uuid4().hex
            request = request.model_copy(update={"conversation_id": conversation_id})
            checksum = self._request_checksum(request)
            history_query = select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id)
            if conversation_id:
                history_query = history_query.where(AssistantMessageModel.conversation_id == conversation_id)
            history = session.scalars(history_query.order_by(AssistantMessageModel.message_order.desc()).limit(_MAX_HISTORY)).all()
        run = self._run(request.run_id)
        projection = self._projection(run)
        stale = request.client_known_state_version is not None and request.client_known_state_version != projection["state_version"]
        semantic_result = classify_semantic_intent(request.message)
        intent = semantic_result.intent
        capability = self._capabilities.dispatch(semantic_result)
        sanitized_question = _safe_question(request.message)
        manifest = {"question_sha256": hashlib.sha256(sanitized_question.encode("utf-8")).hexdigest(), "question_character_count": len(sanitized_question), "projection_item_count": len(projection), "history_item_count": len(history), "intent": intent, "capability_key": capability.capability_key if capability else ""}
        checksum = self._request_checksum(request)
        mutation_request = is_mutation_request(request.message)
        if mutation_request:
            intent = "unsupported"
            capability = None
        if mutation_request and request.conversation_id is None:
            # Keep a refusal isolated from the active answer thread while
            # retaining the durable request/result pair.
            conversation_id = uuid4().hex
        # Commit the conversation and user request before invoking the provider.
        # A separate history reader must be able to observe this pending row.
        with self._scope() as session:
            count = session.scalar(select(AssistantMessageModel.message_order).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order.desc()).limit(1)) or 0
            now = datetime.now(UTC)
            if not session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)):
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            self._persist_user_message(session, request, conversation_id=conversation_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, message_order=int(count) + 1, now=now)
        with self._scope() as session:
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_STARTED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status="started", idempotency_key=request.idempotency_key, payload={"request_id": request.idempotency_key})
        answer, proof = self._compose(intent, projection)
        if mutation_request:
            answer = "This Assistant is read-only and cannot approve gates, execute commands, apply patches, or change workflow state. Use the governed cockpit control for that action."
            proof = "model interpretation"
        governed_response = None
        validated_citations: list[dict[str, object]] = []
        evidence: list[AssistantEvidenceDto] = []
        resolved_capability_key = capability.capability_key if capability is not None else ""
        resolved_model = None
        if not mutation_request and capability is not None:
            try:
                if intent == "evidence_question":
                    with self._scope() as session:
                        evidence_segments, evidence_refs = self._evidence_retrieval.retrieve(session, request.run_id, request.message)
                else:
                    evidence_segments, evidence_refs = [], []
                selected_excerpt_ids = [str(ref["excerpt_id"]) for ref in evidence_refs]
                policy = capability.provider_policy(selected_intent=intent, selected_excerpt_ids=selected_excerpt_ids)
                registry = getattr(self._invocations, "_registry", None)
                provider_contract = build_assistant_response_contract(intent=intent, capability_key=capability.capability_key, selected_excerpt_ids=selected_excerpt_ids, selected_citations=evidence_refs)
                response_contract = build_assistant_response_contract(intent=intent, capability_key=capability.capability_key, selected_excerpt_ids=selected_excerpt_ids, bind_excerpt_ids=False, require_citations=False, enforce_zero_citations=False)
                schema = _azure_strict_schema(provider_contract.model_json_schema())
                prepared = prepare_assistant_request(
                    policy=policy,
                    schema=schema,
                    question=sanitized_question,
                    segments=[LlmContextSegment(segment_id="projection", label="authoritative workflow projection", content=json.dumps({**projection, "evidence": []}, sort_keys=True)), *evidence_segments, LlmContextSegment(segment_id="history", label="recent conversation", content=json.dumps([_safe(item.answer, 300) for item in reversed(history)]))],
                    answer_mode=request.answer_mode,
                )
                manifest["context_budget"] = prepared.manifest["context_budget"]
                manifest["selected_evidence"] = [{key: value for key, value in ref.items() if key != "text" and key != "excerpt_locator"} for ref in evidence_refs if ref["excerpt_id"] in set(prepared.manifest["selected_item_ids"])]
                supplied_ids = set(prepared.manifest["selected_item_ids"])
                evidence_refs = [ref for ref in evidence_refs if ref["excerpt_id"] in supplied_ids]
                manifest["evidence_selection"] = self._evidence_retrieval.last_manifest
                manifest["evidence_selection"]["final_supplied_excerpt_ids"] = sorted(supplied_ids.intersection({ref["excerpt_id"] for ref in evidence_refs}))
                manifest["question_token_count"] = prepared.manifest["context_budget"]["question_tokens"]
                # The final bounded request is now approved and ready for the
                # provider. Persist sanitized preparation metadata before the
                # provider call; raw question/context/evidence never enters
                # this lifecycle payload. The durable idempotency key makes a
                # transport replay a no-op while a user Retry gets a new key.
                with self._scope() as session:
                    self._append_event(
                        session,
                        run_id=request.run_id,
                        conversation_id=conversation_id,
                        message_id=message_id,
                        event_type="ASSISTANT_CONTEXT_BUILT",
                        correlation_id=correlation_id,
                        state_version=int(projection["state_version"]),
                        status="context_built",
                        idempotency_key=request.idempotency_key,
                        payload={
                            "capability_key": capability.capability_key,
                            "answer_mode": prepared.answer_mode,
                            "final_token_count": prepared.final_input_tokens,
                            "selected_count": len(manifest.get("selected_evidence", [])),
                            "omitted_count": len(prepared.manifest.get("omitted_item_ids", [])),
                            "truncated": bool(prepared.manifest.get("truncated_item_ids")),
                            "semantic_state_version": int(projection["state_version"]),
                            "request_manifest_reference": checksum,
                        },
                    )
                governed_response = self._invocations.assistant(AssistantInvocationRequest(run_id=request.run_id, expected_state_version=int(projection["state_version"]), idempotency_key=f"assistant:{request.request_id}", correlation_id=correlation_id, question=prepared.question, context=list(prepared.context), max_output_tokens=prepared.hard_output_cap, prepared_request=prepared, adaptive_answer_target=prepared.adaptive_answer_target, answer_mode=prepared.answer_mode, response_contract=response_contract), actor=actor)
                resolved_model = governed_response.deployment_alias
                if governed_response.status != "completed":
                    if governed_response.failure_code == "LLM_STRUCTURED_RESPONSE_INVALID":
                        raise AssistantRequestError("assistant_invalid_structured_response", "The governed Assistant returned an invalid structured response.", 502)
                    raise AssistantRequestError("assistant_provider_failed", "The governed Assistant provider failed; retry is safe.", 503)
                if governed_response.structured_output.get("intent") != intent or governed_response.structured_output.get("capability_key") != capability.capability_key:
                    raise AssistantRequestError("assistant_invalid_structured_response", "The governed Assistant returned a response for an unexpected capability.", 502)
                citations = governed_response.structured_output.get("citations", [])
                provider_proof = governed_response.structured_output.get("proof_label", "unknown_or_unavailable")
                # Projection-only answers have no evidence allowlist. Clear any
                # provider citations at the authoritative application boundary.
                validated_citations = [] if not evidence_refs else self._validated_citations(citations, evidence_refs, proof_label=provider_proof)
                if validated_citations is None:
                    raise AssistantRequestError("assistant_invalid_citation", "The governed Assistant returned an invalid evidence citation.", 502)
                if isinstance(governed_response.structured_output.get("answer"), str):
                    answer = governed_response.structured_output["answer"]
                    proof = provider_proof
                governed_response = governed_response.model_copy(update={"structured_output": {**governed_response.structured_output, "answer": answer, "proof_label": proof, "citations": validated_citations}})
            except ContextBudgetExceeded:
                self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest={**manifest, "context_budget_failure": "mandatory_content_exceeds_hard_limit"}, checksum=checksum, reason="The Assistant input could not be bounded safely.", code="assistant_context_budget_exceeded", intent=intent, capability_key=resolved_capability_key, model=resolved_model)
                raise AssistantRequestError("assistant_context_budget_exceeded", "The Assistant input could not be bounded safely.", 413)
            except AssistantRequestError as error:
                failed = self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, reason=error.message, code=error.code, intent=intent, capability_key=resolved_capability_key, model=resolved_model)
                error.correlation_id = correlation_id
                error.details = {"message_id": failed.message_id, "conversation_id": failed.conversation_id, "request_id": failed.request_id, "retry_of_message_id": failed.retry_of_message_id}
                raise
            except Exception as error:
                failed = self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, reason="The governed Assistant provider failed; retry is safe.", code="assistant_provider_failed", intent=intent, capability_key=resolved_capability_key, model=resolved_model)
                raise AssistantRequestError("assistant_provider_failed", "The governed Assistant provider failed; retry is safe.", 503, correlation_id=correlation_id, details={"message_id": failed.message_id, "conversation_id": failed.conversation_id, "request_id": failed.request_id, "retry_of_message_id": failed.retry_of_message_id}) from error
        structured = governed_response.structured_output if governed_response is not None else {
            "answer": answer,
            "summary": answer[:240],
            "intent": "unsupported",
            "capability_key": "",
            "proof_label": "model_interpretation" if mutation_request else proof.replace(" ", "_") if proof else "unknown_or_unavailable",
            "citations": [],
            "missing_information": [] if not answer.lower().endswith("unavailable.") else ["authoritative information for this question"],
            "suggested_follow_ups": [],
            "next_step_proposals": [],
            "confidence": "low" if mutation_request else "medium",
        }
        if governed_response is not None and hasattr(self._invocations, "persist_validated_response"):
            # The response artifact must contain the exact final text and
            # citation subset, including the empty proof set after rebuild.
            governed_response = self._invocations.persist_validated_response(governed_response, structured)
        # Projection evidence is never merged into a governed evidence-backed
        # response. The canonical validated citation subset is the only drawer
        # and transport evidence for an Assistant answer.
        if governed_response is not None and structured.get("citations"):
            evidence = [AssistantEvidenceDto(artifact_id=str(item["artifact_id"]), checksum=str(item["checksum_sha256"]), label=str(next((ref.get("label", item["artifact_id"]) for ref in manifest.get("selected_evidence", []) if ref.get("excerpt_id") == item["excerpt_id"]), item["artifact_id"])), excerpt_id=str(item["excerpt_id"]), checksum_sha256=str(item["checksum_sha256"]), stage_key=str(item["stage_key"]), locator=item["locator"], proof_label=str(item["proof_label"])) for item in structured.get("citations", [])]
        elif governed_response is not None and structured.get("proof_label") == "authoritative_persisted_fact":
            evidence = [AssistantEvidenceDto.model_validate(item) for item in projection["evidence"]]
        else:
            evidence = []
        input_tokens = sum(int(item["input_tokens"]) for item in projection["usage"])
        output_tokens = sum(int(item["output_tokens"]) for item in projection["usage"])
        input_cost = sum(float(item.get("input_cost_usd", 0.0)) for item in projection["usage"])
        output_cost = sum(float(item.get("output_cost_usd", 0.0)) for item in projection["usage"])
        total_cost = sum(float(item["cost_usd"]) for item in projection["usage"])
        if governed_response is not None and governed_response.structured_output.get("answer"):
            input_tokens, output_tokens = governed_response.input_tokens, governed_response.output_tokens
            input_cost, output_cost, total_cost = governed_response.input_cost_usd, governed_response.output_cost_usd, governed_response.total_cost_usd
            usage = AssistantUsageDto(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=governed_response.total_tokens, estimated_input_cost=input_cost, estimated_output_cost=output_cost, estimated_total_cost=total_cost)
        else:
            usage = AssistantUsageDto(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens, estimated_input_cost=input_cost, estimated_output_cost=output_cost, estimated_total_cost=total_cost)
        with self._scope() as session:
            prior = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == request.idempotency_key))
            if prior:
                return self._dto(prior, session=session)
            count = session.scalar(select(AssistantMessageModel.message_order).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order.desc()).limit(1)) or 0
            now = datetime.now(UTC)
            if not session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)):
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            else:
                session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)).updated_at = now
            user_key = hashlib.sha256(("user:" + request.idempotency_key).encode()).hexdigest()
            user = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == user_key))
            if user is None:
                self._persist_user_message(session, request, conversation_id=conversation_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, message_order=int(count) + 1, now=now, status="completed")
            else:
                user.status = "completed"
            provenance = {"role": "assistant" if governed_response is not None and governed_response.structured_output.get("answer") else "deterministic_projection", "deployment": governed_response.deployment_alias if governed_response is not None else "none", "prompt": governed_response.prompt_version if governed_response is not None else "none", "schema": governed_response.schema_version if governed_response is not None else "assistant-response-v1", "assistant_v11": {"schema_version": "assistant-response-v1", "validated_response_artifact": {"artifact_id": governed_response.artifact_ids[0], "checksum": governed_response.artifact_checksums[governed_response.artifact_ids[0]]} if governed_response is not None and governed_response.artifact_ids else None, "semantic_classifier": semantic_result.model_dump(mode="json")}}
            row = AssistantMessageModel(id=uuid4().hex, message_id=message_id, conversation_id=conversation_id, run_id=request.run_id, message_order=int(count) + 2, role="assistant", input_manifest=manifest, input_manifest_checksum=checksum, answer=answer, state_version=int(projection["state_version"]), semantic_state_version=int(projection["state_version"]), operational_event_sequence=int(governed_response.event_sequence if governed_response is not None else projection.get("operational_statistics", {}).get("event_sequence", 0) or 0), projection=self._message_projection(projection), evidence=[item.model_dump(mode="json") for item in evidence], proof_label=structured["proof_label"], usage=usage.model_dump(mode="json"), model_provenance=provenance, correlation_id=correlation_id, idempotency_key=request.idempotency_key, request_id=request.request_id, retry_of_message_id=request.retry_of_message_id, intent=structured["intent"], capability_key=structured["capability_key"], answer_mode=request.answer_mode, status="stale" if stale else "completed", created_at=now)
            session.add(row)
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_COMPLETED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status=row.status, idempotency_key=request.idempotency_key, payload={"message_id": message_id})
            return self._dto(row, session=session, stale=stale)

    def history(self, run_id: str, conversation_id: str | None = None, *, actor: str | None = None) -> AssistantHistoryDto:
        self.authorize(run_id, actor or "")
        current_version = int(self._projection(self._run(run_id))["state_version"])
        with self._scope() as session:
            query = select(AssistantMessageModel).where(AssistantMessageModel.run_id == run_id).order_by(AssistantMessageModel.message_order, AssistantMessageModel.id)
            if conversation_id:
                query = query.where(AssistantMessageModel.conversation_id == conversation_id)
            else:
                conversation_id = session.scalar(select(AssistantConversationModel.conversation_id).where(AssistantConversationModel.run_id == run_id).order_by(AssistantConversationModel.updated_at.desc(), AssistantConversationModel.id.desc()).limit(1))
                if conversation_id:
                    query = query.where(AssistantMessageModel.conversation_id == conversation_id)
            rows = session.scalars(query).all()
            conversation = conversation_id or (rows[0].conversation_id if rows else uuid4().hex)
            return AssistantHistoryDto(run_id=run_id, conversation_id=conversation, messages=[self._dto(row, session=session, stale=row.semantic_state_version < current_version) for row in rows])

    @staticmethod
    def _structured_response(row: AssistantMessageModel, session) -> dict[str, object]:
        envelope = (row.model_provenance or {}).get("assistant_v11") or {}
        reference = envelope.get("validated_response_artifact")
        if not isinstance(reference, dict) or not reference.get("artifact_id"):
            return {}
        artifact = session.get(ArtifactMetadataModel, reference["artifact_id"]) or session.get(ArtifactMetadataModel, "metadata-" + reference["artifact_id"])
        run = session.get(MigrationRunModel, row.run_id)
        if artifact is None or run is None or artifact.run_id != row.run_id or artifact.checksum != reference.get("checksum"):
            raise ValueError("validated Assistant response artifact reference is invalid")
        store = LocalFilesystemArtifactStore(Path(run.artifact_root or get_settings().artifact_root), fixed_run_root=Path(run.artifact_root or get_settings().artifact_root))
        payload = json.loads(store.read_artifact(row.run_id, artifact.relative_path).content)
        if not isinstance(payload, dict):
            raise TypeError("validated Assistant response artifact is not an object")
        return payload

    @staticmethod
    def _dto(row: AssistantMessageModel, *, session=None, stale: bool | None = None) -> AssistantMessageResultDto:
        projection = row.projection
        stats = projection.get("operational_statistics")
        structured = AssistantContextService._structured_response(row, session) if session is not None else {}
        legacy = not structured
        proof = structured.get("proof_label", row.proof_label)
        if proof == "authoritative persisted fact": proof = "authoritative_persisted_fact"
        if proof == "unknown or unavailable": proof = "unknown_or_unavailable"
        model = (row.model_provenance or {}).get("deployment") or "deterministic_projection"
        v11_resolved = bool((row.model_provenance or {}).get("assistant_v11", {}).get("schema_version"))
        citations = structured.get("citations", row.evidence if v11_resolved and row.proof_label == "approved_evidence_supported" else [])
        return AssistantMessageResultDto(message_id=row.message_id, model=model, message_order=row.message_order, conversation_id=row.conversation_id, run_id=row.run_id, role=row.role, answer=structured.get("answer", row.answer), current_phase=str(projection.get("phase", "unknown")), current_stage=str(projection.get("stage", "unknown")), workflow_status=str(projection.get("status", "unknown")), current_gate=str(projection.get("gate", "unknown")), current_blocker=str(projection.get("blocker", "unknown")), next_permitted_action=str(projection.get("next_action", "unknown")), workflow_state_version=row.state_version, stale=stale if stale is not None else row.status == "stale", evidence_references=[AssistantEvidenceDto.model_validate(item) for item in row.evidence], proof_label=proof, usage=AssistantUsageDto.model_validate(row.usage), response_status=row.status, failure_reason=row.failure_reason, error_code=(row.model_provenance or {}).get("failure_code"), operational_statistics=AssistantOperationalStatisticsDto.model_validate(stats) if stats else None, request_id=row.request_id, retry_of_message_id=row.retry_of_message_id, intent=structured.get("intent", row.intent if row.intent in {"workflow_status", "blocker_or_failure", "completed_work", "remaining_work", "analysis_explanation", "planning_explanation", "transformation_explanation", "validation_explanation", "evidence_question", "usage_and_cost", "next_steps", "comparison", "unsupported"} else "unsupported"), capability_key=structured.get("capability_key", row.capability_key if not legacy or v11_resolved else ""), summary=structured.get("summary", "unavailable" if legacy else row.answer[:240]), citations=citations, missing_information=structured.get("missing_information", ["V1.1 metadata unavailable for this legacy message"] if legacy else []), suggested_follow_ups=structured.get("suggested_follow_ups", []), next_step_proposals=projection.get("next_step_proposals", structured.get("next_step_proposals", [])), confidence=structured.get("confidence", "unknown_or_unavailable"), correlation_id=row.correlation_id, semantic_state_version=row.semantic_state_version, operational_event_sequence=row.operational_event_sequence, answer_mode=row.answer_mode)
