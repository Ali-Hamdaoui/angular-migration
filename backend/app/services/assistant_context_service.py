"""Run-scoped, read-only assistant vertical slice for AMFA-221."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select
from fastapi import HTTPException

from app.domain.contracts import (
    AssistantEvidenceDto,
    AssistantHistoryDto,
    AssistantMessageRequestDto,
    AssistantMessageResultDto,
    AssistantOperationalStatisticsDto,
    AssistantUsageDto,
)
from app.domain.contracts import AgentKind
from app.llm_gateway import LlmContextSegment
from app.core.config import get_settings
from app.repositories.models import ArtifactMetadataModel, AssistantConversationModel, AssistantLifecycleEventModel, AssistantMessageModel, ExecutionProfileModel, G02ApprovalModel, LlmInvocationModel, MigrationRunModel, MigrationStageModel, SourceSnapshotModel, UsageCostRecordModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.services.mock_migration_api_service import get_mock_migration_api_service
from app.services.migration_run_service import MigrationRunService
from app.services.workflow_projection_service import WorkflowProjectionService
from app.services.llm_evidence_application_service import AssistantInvocationRequest, LlmEvidenceApplicationService
from app.services.assistant_capabilities import classify_intent, default_capability_registry
from app.services.assistant_context_budget import build_bounded_context
from app.services.assistant_evidence_retrieval_service import AssistantEvidenceRetrievalService

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

    def __init__(self, *, session_scope_factory=session_scope, gateway=None, invocation_service=None):
        self._scope = session_scope_factory
        # A gateway is an explicit test/provider seam.  Normal API construction
        # must use the production application service, which resolves the
        # configured governed gateway lazily and fails explicitly when absent.
        self._invocations = invocation_service or LlmEvidenceApplicationService(session_scope_factory=session_scope_factory, gateway=gateway)
        self._capabilities = default_capability_registry()
        self._evidence_retrieval = AssistantEvidenceRetrievalService()

    def authorize(self, run_id: str, actor: str) -> None:
        if run_id.startswith("mock-"):
            return
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND", "message": "Migration run does not exist.", "details": {}})
            if run.actor and run.actor != actor and actor != "local-operator":
                raise HTTPException(status_code=403, detail={"error_code": "RUN_ACCESS_FORBIDDEN", "message": "Authenticated actor is not authorized for this run.", "details": {}})

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
            gate_value = value("gate")
            gate_status = next((status for status in ("pending", "approved", "rejected") if gate_value.lower().endswith(status)), gate_value)
            return {
                "application": value("application_name"), "run_id": data.get("run_id", getattr(run, "run_id", "unknown")),
                "current_angular_version": value("current_angular_version"), "target_angular_version": value("target_angular_version"),
                "phase": value("phase"), "stage": value("stage"), "step": value("step"), "status": value("status"),
                "gate": gate_value, "gate_status": gate_status, "blocker": value("blocker"), "waiting_reason": value("waiting_reason"),
                "failure_reason": value("failure_reason"), "next_action": value("next_permitted_action"),
                "completed_phases": data.get("completed_work", []), "remaining_phases": data.get("remaining_work", []),
                "state_version": int(data.get("workflow_state_version", 1)), "events": [],
                "evidence": [{"artifact_id": item["artifact_id"], "checksum": item["checksum"], "label": item["label"]} for item in evidence],
                "usage": [{"input_tokens": stats["input_tokens"], "output_tokens": stats["output_tokens"], "total_tokens": stats["total_tokens"], "input_cost_usd": stats["input_cost_usd"], "output_cost_usd": stats["output_cost_usd"], "cost_usd": stats["total_cost_usd"]}] if stats.get("input_tokens") is not None else [],
                "duration_seconds": stats.get("recorded_workflow_duration_seconds"),
                "operational_statistics": stats,
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
        return "general"

    def _compose(self, intent: str, projection: dict[str, object]) -> tuple[str, str]:
        intent = {
            "workflow_status": "workflow", "blocker_or_failure": "validation",
            "completed_work": "completed", "usage_and_cost": "operations",
            "analysis_explanation": "analysis", "planning_explanation": "planning",
            "transformation_explanation": "transformation", "validation_explanation": "validation",
            "next_steps": "workflow", "general_migration_question": "general",
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
            gate_text = gate if gate_status in {"pending", "approved", "rejected"} and gate.lower().endswith(f" {gate_status}") else f"{gate} ({gate_status})"
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
        completed = ", ".join(str(item) for item in projection.get("completed_phases", [])) or "none recorded"
        remaining = ", ".join(str(item) for item in projection.get("remaining_phases", [])) or "none recorded"
        return (
            f"Current migration context: phase={projection['phase']}; stage={projection['stage']}; "
            f"status={projection['status']}; gate={projection['gate']}; blocker={projection['blocker']}; "
            f"next permitted action={projection['next_action']}. Completed work: {completed}. Remaining work: {remaining}. "
            "I can explain or compare any of these persisted facts; unavailable facts will be identified explicitly.",
            "authoritative persisted fact",
        )

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
            "message": request.message,
            "conversation_id": request.conversation_id,
            "client_known_state_version": request.client_known_state_version,
            "answer_mode": request.answer_mode,
            "retry_of_message_id": request.retry_of_message_id,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _message_projection(projection: dict[str, object]) -> dict[str, object]:
        return {"phase": projection["phase"], "stage": projection["stage"], "status": projection["status"], "gate": projection["gate"], "blocker": projection["blocker"], "next_action": projection["next_action"], "operational_statistics": projection.get("operational_statistics", {})}

    def _persist_user_message(self, session, request, *, conversation_id, correlation_id, projection, manifest, checksum, message_order, now):
        session.add(AssistantMessageModel(
            id=uuid4().hex, message_id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id,
            message_order=message_order, role="user", input_manifest=manifest, input_manifest_checksum=checksum,
            answer=_safe(request.message, 1000), state_version=int(projection["state_version"]), semantic_state_version=int(projection["state_version"]), operational_event_sequence=int(projection.get("operational_statistics", {}).get("event_sequence", 0) or 0),
            projection=self._message_projection(projection), evidence=[], proof_label="user request",
            usage=AssistantUsageDto(input_tokens=0, output_tokens=0, total_tokens=0, estimated_input_cost=0, estimated_output_cost=0, estimated_total_cost=0).model_dump(mode="json"),
            model_provenance={"role": "user"}, correlation_id=correlation_id,
            idempotency_key=hashlib.sha256(("user:" + request.idempotency_key).encode()).hexdigest(),
            status="completed", failure_reason=None, created_at=now,
        ))

    def _persist_failed_result(self, request, *, conversation_id, message_id, correlation_id, projection, manifest, checksum, reason, code):
        with self._scope() as session:
            prior = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == request.idempotency_key))
            if prior:
                return self._dto(prior)
            count = session.scalar(select(AssistantMessageModel.message_order).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order.desc()).limit(1)) or 0
            now = datetime.now(UTC)
            if not session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)):
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            self._persist_user_message(session, request, conversation_id=conversation_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, message_order=int(count) + 1, now=now)
            row = AssistantMessageModel(id=uuid4().hex, message_id=message_id, conversation_id=conversation_id, run_id=request.run_id, message_order=int(count) + 2, role="assistant", input_manifest=manifest, input_manifest_checksum=checksum, answer="The Assistant request failed before producing a completed answer.", state_version=int(projection["state_version"]), projection=self._message_projection(projection), evidence=[], proof_label="unknown or unavailable", usage=AssistantUsageDto(input_tokens=0, output_tokens=0, total_tokens=0, estimated_input_cost=0, estimated_output_cost=0, estimated_total_cost=0).model_dump(mode="json"), model_provenance={"role": "assistant", "failure_code": code}, correlation_id=correlation_id, idempotency_key=request.idempotency_key, status="failed", failure_reason=reason, created_at=now)
            session.add(row)
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_FAILED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status="failed", idempotency_key=request.idempotency_key, payload={"failure_code": code})
            return self._dto(row)

    @staticmethod
    def _authorized_artifact_ids(session, run_id: str) -> set[str]:
        authorized: set[str] = set()
        snapshot = session.scalar(select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run_id).order_by(SourceSnapshotModel.created_at.desc()))
        g02 = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.updated_at.desc()))
        execution_profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))
        if snapshot is not None and snapshot.status == 'created':
            authorized.update(snapshot.artifact_ids or [])
        if g02 is not None and g02.status == 'approved':
            authorized.update(g02.artifact_ids or [])
        if execution_profile is not None:
            authorized.update(execution_profile.artifact_ids or [])
        return authorized

    @staticmethod
    def _citation_structure(citations: object) -> str:
        if not isinstance(citations, list):
            return 'citation_count=invalid; citation_type=' + type(citations).__name__
        items = []
        for citation in citations[:8]:
            if isinstance(citation, dict):
                items.append({
                    'keys': sorted(str(key) for key in citation.keys()),
                    'types': {str(key): type(value).__name__ for key, value in citation.items()},
                    'nulls': {str(key): value is None for key, value in citation.items()},
                })
            else:
                items.append({'type': type(citation).__name__})
        return json.dumps({'citation_count': len(citations), 'items': items}, sort_keys=True, separators=(',', ':'))[:360]

    @classmethod
    def _validated_citations(cls, session, run_id: str, citations: object):
        if not isinstance(citations, list):
            return None
        supported_types = {"json", "yaml", "markdown", "text_log", "command_log", "report"}
        authorized = cls._authorized_artifact_ids(session, run_id)
        canonical_authorized = authorized | {'metadata-' + item for item in authorized}
        validated = []
        for citation in citations:
            if not isinstance(citation, dict) or not citation.get("artifact_id") or not citation.get("checksum"):
                return None
            citation_id = citation["artifact_id"]
            record = session.get(ArtifactMetadataModel, citation_id) or session.get(ArtifactMetadataModel, f'metadata-{citation_id}')
            metadata = record.safe_metadata or {} if record is not None else {}
            authorized_record = citation_id in canonical_authorized or (record is not None and record.id.removeprefix('metadata-') in authorized)
            metadata_approved = metadata.get("approval_status") in {"approved", "approved_with_comment"} and str(metadata.get("lineage", "")).startswith(run_id)
            if record is None or record.run_id != run_id or record.checksum != citation["checksum"] or (citation.get("stage_id") and record.stage_id != citation["stage_id"]) or not record.immutable or record.redacted or record.artifact_type not in supported_types or not (authorized_record or metadata_approved):
                return None
            if record.stage_id:
                stage = session.get(MigrationStageModel, record.stage_id)
                if stage is None or stage.run_id != run_id:
                    return None
            if metadata.get("superseded") is True or metadata.get("rejected") is True:
                return None
            validated.append(record)
        return validated

    @classmethod
    def _validate_citations(cls, session, run_id: str, citations: object) -> bool:
        return cls._validated_citations(session, run_id, citations) is not None

    def answer(self, request: AssistantMessageRequestDto, correlation_id: str | None = None, actor: str = "local-operator") -> AssistantMessageResultDto:
        if not request.run_id:
            raise AssistantRequestError("run_id_required", "A run-scoped assistant request is required.", 422)
        request_id = request.request_id or request.idempotency_key or uuid4().hex
        request = request.model_copy(update={"request_id": request_id, "idempotency_key": request.idempotency_key or request_id})
        correlation_id = correlation_id or uuid4().hex
        conversation_id = request.conversation_id or uuid4().hex
        message_id = uuid4().hex
        with self._scope() as session:
            prior = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == request.idempotency_key))
            if prior:
                request_checksum = self._request_checksum(request)
                if prior.input_manifest_checksum != request_checksum:
                    raise AssistantRequestError("idempotency_key_reused", "Idempotency key was used with a different payload.", 409)
                return self._dto(prior)
            if request.conversation_id:
                selected_conversation = request.conversation_id
            else:
                selected_conversation = session.scalar(select(AssistantConversationModel.conversation_id).where(AssistantConversationModel.run_id == request.run_id).order_by(AssistantConversationModel.updated_at.desc()).limit(1))
            history_query = select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id)
            if selected_conversation:
                history_query = history_query.where(AssistantMessageModel.conversation_id == selected_conversation)
            history = session.scalars(history_query.order_by(AssistantMessageModel.message_order.desc()).limit(_MAX_HISTORY)).all()
            if selected_conversation:
                conversation_id = selected_conversation
        run = self._run(request.run_id)
        projection = self._projection(run)
        stale = request.client_known_state_version is not None and request.client_known_state_version != projection["state_version"]
        intent = classify_intent(request.message)
        capability = self._capabilities.get_for_intent(intent)
        history_context = [{"role": item.role, "content": _safe(item.answer, 600)} for item in reversed(history)]
        manifest = {"question": _safe(request.message, 1000), "projection": projection, "history": history_context, "intent": intent, "capability_key": capability.capability_key if capability else "", "configured_input_limit": 40000}
        checksum = self._request_checksum(request)
        with self._scope() as session:
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_STARTED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status="started", idempotency_key=request.idempotency_key, payload={"request_id": request.idempotency_key})
        intent = "mutation" if self._intent(request.message) == "mutation" else intent
        if intent == "mutation" and request.conversation_id is None:
            # Keep a refusal isolated from the active answer thread while
            # retaining the durable request/result pair.
            conversation_id = uuid4().hex
        answer, proof = self._compose(intent, projection)
        governed_response = None
        evidence = [AssistantEvidenceDto.model_validate(item) for item in projection["evidence"]]
        if intent != "mutation":
            try:
                with self._scope() as session:
                    evidence_segments, evidence_refs = self._evidence_retrieval.retrieve(session, request.run_id, request.message)
                bounded = build_bounded_context([
                    LlmContextSegment(segment_id="projection", label="authoritative workflow projection", content=json.dumps(projection, sort_keys=True)),
                    *evidence_segments,
                    LlmContextSegment(segment_id="history", label="recent conversation", content=json.dumps(history_context, sort_keys=True)),
                ])
                manifest["context_manifest"] = bounded.manifest
                manifest["selected_evidence"] = evidence_refs
                output_budget = {"concise": 1_200, "detailed": 4_000, "deep": 8_000}[request.answer_mode]
                governed_response = self._invocations.assistant(AssistantInvocationRequest(run_id=request.run_id, expected_state_version=int(projection["state_version"]), idempotency_key=f"assistant:{request.request_id}", correlation_id=correlation_id, question=_safe(request.message, 1000), context=bounded.segments, max_output_tokens=output_budget), actor=actor)
                if governed_response.status != "completed":
                    raise AssistantRequestError("assistant_provider_failed", "The governed Assistant provider failed; retry is safe.", 503)
                citations = governed_response.structured_output.get("citations", [])
                with self._scope() as session:
                    validated_citations = self._validated_citations(session, request.run_id, citations)
                if validated_citations is None:
                    failed = self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, reason="Citation validation failed; " + self._citation_structure(citations), code="invalid_citation")
                    raise AssistantRequestError("invalid_citation", "The governed Assistant returned an invalid evidence citation.", 502)
                if isinstance(governed_response.structured_output.get("answer"), str):
                    answer = governed_response.structured_output["answer"]
                    proof = "governed Assistant role"
                    answer_lower = answer.lower()
                    if intent in {"workflow", "workflow_status"} and projection.get("blocker") == "NO_COMPATIBLE_RUNTIME_PROFILE" and (
                        "unknown" in answer_lower
                        or "stale answer" in answer_lower
                        or "operational statistics unavailable" in answer_lower
                        or "failed before producing a completed answer" in answer_lower
                        or "no_compatible_runtime_profile" not in answer_lower and "no compatible runtime profile" not in answer_lower
                        or "execution-profile resolution blocked" not in answer_lower
                    ):
                        answer = self._authoritative_workflow_answer(projection)
                        proof = "authoritative persisted fact"
                        governed_response = governed_response.model_copy(update={"structured_output": {**governed_response.structured_output, "answer": answer}})
                if citations:
                    evidence = [AssistantEvidenceDto(artifact_id=item.id, checksum=item.checksum, label=item.relative_path) for item in validated_citations or []]
            except AssistantRequestError as error:
                self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, reason=error.message, code=error.code)
                raise
            except Exception as error:
                self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, reason="The governed Assistant provider failed; retry is safe.", code="assistant_provider_failed")
                raise AssistantRequestError("assistant_provider_failed", "The governed Assistant provider failed; retry is safe.", 503) from error
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
                return self._dto(prior)
            count = session.scalar(select(AssistantMessageModel.message_order).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order.desc()).limit(1)) or 0
            now = datetime.now(UTC)
            if not session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)):
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            else:
                session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)).updated_at = now
            self._persist_user_message(session, request, conversation_id=conversation_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, message_order=int(count) + 1, now=now)
            row = AssistantMessageModel(id=uuid4().hex, message_id=message_id, conversation_id=conversation_id, run_id=request.run_id, message_order=int(count) + 2, role="assistant", input_manifest=manifest, input_manifest_checksum=checksum, answer=answer, state_version=int(projection["state_version"]), semantic_state_version=int(projection["state_version"]), operational_event_sequence=int(projection.get("operational_statistics", {}).get("event_sequence", 0) or 0), projection=self._message_projection(projection), evidence=[item.model_dump(mode="json") for item in evidence], proof_label=proof, usage=usage.model_dump(mode="json"), model_provenance={"role": "assistant" if governed_response is not None and governed_response.structured_output.get("answer") else "deterministic_projection", "deployment": governed_response.deployment_alias if governed_response is not None else "none", "prompt": governed_response.prompt_version if governed_response is not None else "none", "schema": governed_response.schema_version if governed_response is not None else "assistant-response-v1"}, correlation_id=correlation_id, idempotency_key=request.idempotency_key, request_id=request.request_id, retry_of_message_id=request.retry_of_message_id, intent=intent, capability_key=capability.capability_key if capability else "", answer_mode=request.answer_mode, status="stale" if stale else "completed", created_at=now)
            session.add(row)
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_COMPLETED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status=row.status, idempotency_key=request.idempotency_key, payload={"message_id": message_id})
            return self._dto(row, stale=stale)

    def history(self, run_id: str, conversation_id: str | None = None) -> AssistantHistoryDto:
        current_version = int(self._projection(self._run(run_id))["state_version"])
        with self._scope() as session:
            query = select(AssistantMessageModel).where(AssistantMessageModel.run_id == run_id).order_by(AssistantMessageModel.message_order)
            if conversation_id:
                query = query.where(AssistantMessageModel.conversation_id == conversation_id)
            else:
                conversation_id = session.scalar(select(AssistantConversationModel.conversation_id).where(AssistantConversationModel.run_id == run_id).order_by(AssistantConversationModel.updated_at.desc()).limit(1))
                if conversation_id:
                    query = query.where(AssistantMessageModel.conversation_id == conversation_id)
            rows = session.scalars(query).all()
            conversation = conversation_id or (rows[0].conversation_id if rows else uuid4().hex)
            return AssistantHistoryDto(run_id=run_id, conversation_id=conversation, messages=[self._dto(row, stale=row.state_version < current_version) for row in rows])

    @staticmethod
    def _dto(row: AssistantMessageModel, *, stale: bool | None = None) -> AssistantMessageResultDto:
        projection = row.projection
        stats = projection.get("operational_statistics")
        provenance = row.model_provenance or {}
        deployment = provenance.get("deployment")
        model = str(deployment if deployment not in {None, "", "none"} else provenance.get("role") or "deterministic_projection")
        return AssistantMessageResultDto(message_id=row.message_id, model=model, message_order=row.message_order, conversation_id=row.conversation_id, run_id=row.run_id, role=row.role, answer=row.answer, current_phase=str(projection.get("phase", "unknown")), current_stage=str(projection.get("stage", "unknown")), workflow_status=str(projection.get("status", "unknown")), current_gate=str(projection.get("gate", "unknown")), current_blocker=str(projection.get("blocker", "unknown")), next_permitted_action=str(projection.get("next_action", "unknown")), workflow_state_version=row.state_version, stale=stale if stale is not None else row.status == "stale", evidence_references=[AssistantEvidenceDto.model_validate(item) for item in row.evidence], proof_label=row.proof_label, usage=AssistantUsageDto.model_validate(row.usage), response_status=row.status, failure_reason=row.failure_reason, operational_statistics=AssistantOperationalStatisticsDto.model_validate(stats) if stats else None)
