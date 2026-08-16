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
from app.artifact_store import ArtifactNotFoundError, ArtifactStoreError, LocalFilesystemArtifactStore
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
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    SourceSnapshotModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.assistant_capabilities import classify_semantic_intent, default_capability_registry, is_mutation_request
from app.services.assistant_context_budget import MAX_INPUT_TOKENS, ContextBudgetExceeded, build_bounded_context, prepare_assistant_request
from app.services.assistant_evidence_retrieval_service import AssistantEvidenceRetrievalService
from app.services.llm_evidence_application_service import AssistantInvocationRequest, LlmEvidenceApplicationService, build_assistant_response_contract
from app.llm_gateway.azure_gateway import _azure_strict_schema
from app.services.migration_run_service import MigrationRunService
from app.services.mock_migration_api_service import get_mock_migration_api_service
from app.services.workflow_projection_service import WorkflowProjectionService

_SECRET = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+")
_PATH = re.compile(r"(?i)([a-z]:\\|/home/|/Users/|/workspace/)[^\s,;]+")
_MAX_HISTORY = 12
_MAX_RECENT_EVENTS = 12
_MAX_REPAIR_ITEMS = 8
_GREETING = "Hi! I can help you understand this migration. Ask me what's happening, what failed, what needs approval, or what changed."
_TERMINAL_STATUSES = {"COMPLETED"}
_STAGE_ROUTE = re.compile(r"angular-(\d+)(?:\.x)?-to-(\d+)(?:\.x)?(?:--[a-z0-9-]+)?", re.IGNORECASE)
_RAW_PROJECTION = re.compile(r"\b(?:phase|stage|status|gate|blocker)\s*=", re.IGNORECASE)
_TECHNICAL_QUESTION = re.compile(r"\b(?:technical|details?|id|identifier|checksum|state[_ ]version|raw|json|payload|event)\b", re.IGNORECASE)


class AssistantRequestError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409, details: dict[str, object] | None = None, *, correlation_id: str | None = None):
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
    """Sanitize the complete user question without semantic truncation."""
    text = _SECRET.sub("[REDACTED]", str(value or ""))
    return _PATH.sub("[REDACTED_PATH]", text)


def _bounded_strings(value: object, *, limit: int = _MAX_REPAIR_ITEMS, item_limit: int = 240) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_safe(item, item_limit) for item in value[:limit] if str(item or "").strip()]


def _is_greeting(question: str) -> bool:
    normalized = re.sub(r"[^a-z]+", " ", question.casefold()).strip()
    return normalized in {"hi", "hey", "hello", "hi there", "hey there", "hello there", "good morning", "good afternoon", "good evening"}


def _display_stage(value: object) -> str:
    text = str(value or "").strip()
    match = _STAGE_ROUTE.search(text)
    if match:
        return f"Angular {match.group(1)} → {match.group(2)}"
    if not text or text.casefold() in {"unknown", "none", "unavailable"}:
        return "the current migration stage"
    return "the current migration stage" if "--" in text else text


def _display_gate(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in {"unknown", "none", "unavailable"}:
        return "human review status is unavailable"
    match = re.search(r"\bG\d+\b\s*(pending|approved|rejected)?", text, re.IGNORECASE)
    status = (match.group(1) if match else "").casefold()
    return {
        "pending": "human review is pending",
        "approved": "human review is approved",
        "rejected": "human review was rejected",
    }.get(status, "human review is required")


def _current_status(projection: dict[str, object]) -> str:
    return str(projection.get("status") or "unknown").upper()


def _display_phase(value: object) -> str:
    text = str(value or "").strip().replace("_", " ").lower()
    return text.title() if text and text not in {"unknown", "unavailable", "none"} else "the current phase"


def _human_workflow_answer(projection: dict[str, object]) -> str:
    stage = _display_stage(projection.get("stage"))
    status = _current_status(projection)
    if status == "COMPLETED":
        return f"{stage} has completed. The migration is now complete."
    if str(projection.get("blocker", "none")).casefold() not in {"", "none", "unknown", "unavailable"}:
        return "The migration is currently blocked. Ask what failed for the current evidence and next permitted action."
    if str(projection.get("gate_status", "")).casefold() == "pending":
        return f"The migration is in {_display_phase(projection.get('phase'))} at {stage} and is waiting for human review."
    return f"The migration is in {_display_phase(projection.get('phase'))} at {stage}. No current blocker is recorded."


def _humanize_primary_answer(answer: object, projection: dict[str, object], question: str = "") -> str:
    text = str(answer or "").strip()
    if not text or _TECHNICAL_QUESTION.search(question):
        return text
    if _RAW_PROJECTION.search(text) or text.casefold().startswith("current migration context:"):
        return _human_workflow_answer(projection)
    text = _STAGE_ROUTE.sub(lambda match: f"Angular {match.group(1)} → {match.group(2)}", text)
    text = re.sub(r"\bG\d+\b\s*(pending|approved|rejected)?", lambda match: {
        "pending": "pending human review",
        "approved": "approved human review",
        "rejected": "rejected human review",
    }.get((match.group(1) or "").casefold(), "the relevant human review") + " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\ba\s+the relevant human review\b", "a human review", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthe relevant human review\s+recovery\b", "the earlier recovery", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthe relevant human review\s+is\s+approved\b", "human review is approved", text, flags=re.IGNORECASE)
    text = re.sub(r"\blatest:\s+approved human review\s*", "latest review approved", text, flags=re.IGNORECASE)
    text = re.sub(r"\ball human gates\s*\([^)]*approved human review\s*\)", "all human gates are approved", text, flags=re.IGNORECASE)
    text = re.sub(r"\brepair_state\s+is\s+not_required\b", "no repair is currently required", text, flags=re.IGNORECASE)
    text = re.sub(r"\battempt_number=\d+,\s*parent attempt exists\b", "the latest repair builds on an earlier attempt", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfailure_classification\s+is\s+[\"']?unavailable[\"']?\s+and\s+failure_reason\s+is\s+[\"']?unknown[\"']?", "no current failure classification or reason is recorded", text, flags=re.IGNORECASE)
    text = re.sub(r"\bstatus:\s*COMPLETED\b", "the migration is complete", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:workflow\s+)?state[_ ]version\s*[:=]\s*\d+\b[.;]?", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip()


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

    def _run(self, run_id: str, *, with_projection: bool = True):
        if run_id.startswith("mock-"):
            return get_mock_migration_api_service().get_state(run_id).model_copy(update={"run_id": run_id, "llm_usage": []})
        with self._scope() as session:
            persisted = session.get(MigrationRunModel, run_id)
            if persisted is not None:
                # The shared projection is the only consumer of persisted run
                # data in the modern path; the legacy fields below exist only
                # for the pre-projection fallback and are never populated here.
                projection = WorkflowProjectionService().build(session, run_id) if with_projection else None
                recent_events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence.desc()).limit(_MAX_RECENT_EVENTS)).all())
                repair = session.scalar(select(RepairAttemptModel).where(RepairAttemptModel.run_id == run_id).order_by(RepairAttemptModel.attempt_number.desc(), RepairAttemptModel.updated_at.desc()).limit(1))
                return SimpleNamespace(run_id=run_id, status=persisted.status, run_phase=persisted.run_phase, state_version=persisted.state_version, source_angular_version=persisted.source_angular_version, target_angular_version=persisted.target_angular_version, created_at=persisted.created_at, updated_at=persisted.updated_at, stages=[], workflow_events=list(reversed(recent_events)), artifacts=[], llm_usage=[], assistant_projection=projection, assistant_repair=self._repair_context(session, persisted, repair))
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
            evidence = (data.get("evidence_references") or [])[:_MAX_REPAIR_ITEMS]
            recent_events = [
                {
                    "type": str(event.event_type),
                    "sequence": int(event.sequence),
                    "occurred_at": event.occurred_at.isoformat() if isinstance(event.occurred_at, datetime) else None,
                    "stage_id": event.stage_id,
                    "summary": _safe(event.payload.get("failure_reason") or event.payload.get("error_code") or event.reason or event.event_type, 240),
                }
                for event in list(getattr(run, "workflow_events", []))[-_MAX_RECENT_EVENTS:]
            ]
            latest_command_value = data.get("latest_command_result") or {}
            latest_command = latest_command_value.get("value") if latest_command_value.get("availability") == "known" else None
            gate_value = value("gate")
            gate_status = next((status for status in ("pending", "approved", "rejected") if gate_value.lower().endswith(status)), gate_value)
            status_value = value("status")
            raw_blocker = value("blocker")
            historical_failures = [raw_blocker] if _current_status({"status": status_value}) in _TERMINAL_STATUSES and raw_blocker.casefold() not in {"", "none", "unknown", "unavailable"} else []
            return {
                "application": value("application_name"), "run_id": data.get("run_id", getattr(run, "run_id", "unknown")),
                "current_angular_version": value("current_angular_version"), "target_angular_version": value("target_angular_version"),
                "phase": value("phase"), "stage": value("stage"), "step": value("step"), "status": status_value,
                "gate": gate_value, "gate_status": gate_status, "blocker": "none" if historical_failures else raw_blocker, "historical_failures": historical_failures, "waiting_reason": value("waiting_reason"),
                "failure_reason": "unknown" if historical_failures else value("failure_reason"), "next_action": value("next_permitted_action"),
                "completed_phases": data.get("completed_work", []), "remaining_phases": data.get("remaining_work", []),
                "state_version": int(data.get("semantic_state_version", data.get("workflow_state_version", 1))), "events": recent_events,
                "next_step_proposals": data.get("next_step_proposals", []),
                "failure_classification": "unavailable" if historical_failures else value("failure_classification"),
                "repair_state": value("repair_state"),
                "repair_context": getattr(run, "assistant_repair", {"availability": "unavailable"}),
                "latest_command_result": latest_command,
                "evidence": [{"artifact_id": item["artifact_id"], "checksum": item["checksum"], "label": item["label"]} for item in evidence],
                "usage": [{"input_tokens": stats["input_tokens"], "output_tokens": stats["output_tokens"], "total_tokens": stats["total_tokens"], "input_cost_usd": stats["input_cost_usd"], "output_cost_usd": stats["output_cost_usd"], "cost_usd": stats["total_cost_usd"]}] if stats.get("input_tokens") is not None else [],
                "duration_seconds": stats.get("recorded_workflow_duration_seconds"),
                "operational_statistics": stats,
                "operational_event_sequence": data.get("operational_event_sequence", 0),
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
        historical_failures = [blocker] if _current_status({"status": str(status_value)}) in _TERMINAL_STATUSES and blocker.casefold() not in {"", "none", "unknown", "unavailable"} else []
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
            "blocker": "none" if historical_failures else blocker,
            "historical_failures": historical_failures,
            "gate_status": "pending" if g02_pending else "unknown",
            "waiting_reason": waiting_reason,
            "failure_reason": "unknown" if historical_failures else failure_reason,
            "next_action": "Record a G02 reviewer decision through the governed cockpit control." if g02_pending else "unknown",
            "completed_phases": completed or ["unknown"],
            "remaining_phases": remaining,
            "state_version": max(1, int(getattr(run, "state_version", 1) or 1), max((int(event.payload.get("next_state_version", 1)) for event in events), default=1)),
            "events": [{"type": event.event_type, "sequence": event.sequence} for event in events[-20:]],
            "next_step_proposals": [],
            "failure_classification": failure_reason if failure_reason != "unknown" else "unavailable",
            "evidence": evidence,
            "usage": [{"input_tokens": item.input_tokens, "output_tokens": item.output_tokens, "total_tokens": item.total_tokens, "input_cost_usd": getattr(item, "input_cost_usd", 0.0), "output_cost_usd": getattr(item, "output_cost_usd", 0.0), "cost_usd": getattr(item, "total_cost_usd", getattr(item, "cost_usd", 0.0))} for item in getattr(run, "llm_usage", [])],
            "duration_seconds": AssistantContextService._recorded_workflow_duration_seconds(run),
            "operational_statistics": {},
            "operational_event_sequence": latest.sequence if latest is not None else 0,
        }

    @staticmethod
    def _artifact_json(session, run, artifact_id: str | None, checksum: str | None) -> dict[str, object] | None:
        if not artifact_id or not checksum:
            return None
        metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id) or session.get(ArtifactMetadataModel, artifact_id)
        if metadata is None or metadata.run_id != run.id or not metadata.immutable or metadata.checksum != checksum:
            return None
        root = Path(run.artifact_root or get_settings().artifact_root)
        try:
            stored = LocalFilesystemArtifactStore(root, fixed_run_root=root).read_artifact(run.id, metadata.relative_path)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError):
            return None
        if stored.ref.run_id != run.id or stored.ref.artifact_id != artifact_id or stored.ref.checksum != checksum:
            return None
        try:
            payload = json.loads(stored.content)
        except (TypeError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _repair_context(cls, session, run, attempt) -> dict[str, object]:
        if attempt is None:
            return {"availability": "unavailable"}
        proposal = cls._artifact_json(session, run, attempt.proposal_artifact_id, attempt.proposal_checksum)
        review = cls._artifact_json(session, run, attempt.review_artifact_id, attempt.review_checksum)
        return {
            "availability": "known",
            "state": _safe(run.repair_status),
            "attempt_number": attempt.attempt_number,
            "status": _safe(attempt.status),
            "risk_level": _safe(attempt.risk_level),
            "parent_attempt_exists": attempt.parent_attempt_id is not None,
            "diagnosis": _safe(attempt.diagnosis, 600),
            "proposal": {
                "available": proposal is not None,
                "risk_level": _safe((proposal or {}).get("risk_level")),
                "rationale": _bounded_strings((proposal or {}).get("rationale")),
                "touched_files": _bounded_strings((proposal or {}).get("touched_files"), item_limit=160),
                "validation_targets": _bounded_strings((proposal or {}).get("validation_targets"), item_limit=80),
            },
            "review": {
                "available": review is not None,
                "decision": _safe((review or {}).get("decision")),
                "findings": _bounded_strings((review or {}).get("findings")),
                "risk_assessment": _safe((review or {}).get("risk_assessment"), 600),
                "required_validation_targets": _bounded_strings((review or {}).get("required_validation_targets"), item_limit=80),
            },
        }

    @staticmethod
    def _intent(question: str) -> str:
        q = question.lower()
        punctuation = ",.;:!?"
        clean = q.translate(str.maketrans("", "", punctuation))
        clean_words = set(clean.split())
        mutation_keywords = {"approve", "reject", "execute", "apply", "patch"}
        if mutation_keywords & clean_words:
            return "mutation"
        if "change" in clean_words and ("workflow" in clean_words or "state" in clean_words):
            return "mutation"
        if "run" in clean_words and "command" in clean_words:
            return "mutation"
        if "modify" in clean_words and "files" in clean_words:
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

    def _compose(self, intent: str, projection: dict[str, object], question: str = "") -> tuple[str, str]:
        intent = {
            "workflow_status": "workflow", "blocker_or_failure": "validation",
            "completed_work": "completed", "usage_and_cost": "operations",
            "analysis_explanation": "analysis", "planning_explanation": "planning",
            "transformation_explanation": "transformation", "validation_explanation": "validation",
            "next_steps": "workflow", "remaining_work": "completed", "comparison": "workflow",
            "evidence_question": "analysis", "general_migration_question": "general",
        }.get(intent, intent)
        if intent == "mutation":
            return "This Assistant is read-only and cannot approve gates, execute commands, apply patches, or change workflow state. Use the governed cockpit control for that action.", "model interpretation"
        if intent == "workflow":
            return _human_workflow_answer(projection), "authoritative persisted fact"
        if intent == "completed":
            completed = [_display_stage(item) if "angular-" in str(item).casefold() else str(item) for item in projection.get("completed_phases", [])]
            remaining = [_display_stage(item) if "angular-" in str(item).casefold() else str(item) for item in projection.get("remaining_phases", [])]
            return f"Completed work includes: {', '.join(completed) or 'no completed stages are recorded'}. Remaining work includes: {', '.join(remaining) or 'none recorded'}.", "authoritative persisted fact"
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
        if _is_greeting(question):
            return _GREETING, "model interpretation"
        return "I can help you understand this migration. Ask me what's happening, what failed, what needs approval, or what changed.", "model interpretation"

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
            "client_known_state_version": request.client_known_state_version,
            "answer_mode": request.answer_mode,
            "retry_of_message_id": request.retry_of_message_id,
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
        return {"phase": projection["phase"], "stage": projection["stage"], "status": projection["status"], "gate": projection["gate"], "blocker": projection["blocker"], "historical_failures": projection.get("historical_failures", []), "next_action": projection["next_action"], "next_step_proposals": projection.get("next_step_proposals", []), "failure_classification": projection.get("failure_classification", "unavailable"), "repair_state": projection.get("repair_state", "unknown"), "repair_context": projection.get("repair_context", {"availability": "unavailable"}), "latest_command_result": projection.get("latest_command_result"), "events": projection.get("events", []), "operational_statistics": projection.get("operational_statistics", {})}

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

    @staticmethod
    def _provider_failure(response) -> AssistantRequestError:
        code = response.failure_code or "assistant_provider_failed"
        status = {"LLM_CONFIGURATION_INCOMPLETE": 409, "RUN_NOT_FOUND": 404, "RUN_NOT_AUTHORIZED": 403, "STALE_STATE_VERSION": 409, "IDEMPOTENCY_KEY_REUSED": 409}.get(code, 502 if code in {"protocol", "schema", "semantic", "empty_output", "LLM_STRUCTURED_RESPONSE_INVALID"} else 503)
        message = "The governed Assistant provider failed; retry is safe."
        if code == "LLM_CONFIGURATION_INCOMPLETE":
            message = "The governed Assistant provider is not configured."
        return AssistantRequestError(code, message, status, {key: value for key, value in {
            "retryable": response.retryable, "request_id": response.provider_request_id,
            "failure_stage": response.failure_stage, "failure_subtype": response.failure_subtype,
            "provider_status": response.provider_http_status, "provider_error_code": response.provider_error_code,
            "provider_message": getattr(response, "sanitized_provider_message", None), "deployment": response.deployment_alias,
            "response_kind": response.response_kind, "response_received": response.response_received,
            "transport_started": response.transport_started,
        }.items() if value is not None})

    @staticmethod
    def _provider_provenance(response) -> dict[str, object]:
        if response is None:
            return {"role": "assistant"}
        return {"role": "assistant", "provider": response.provider, "deployment": response.deployment_alias, "prompt": response.prompt_version, "schema": response.schema_version, "failure_code": response.failure_code, "diagnostics": {"http_status": response.provider_http_status, "error_code": response.provider_error_code, "request_id": response.provider_request_id, "failure_stage": response.failure_stage, "failure_subtype": response.failure_subtype, "retryable": response.retryable, "response_received": response.response_received, "response_kind": response.response_kind, "transport_started": response.transport_started}}

    def _persist_failed_result(self, request, *, conversation_id, message_id, correlation_id, projection, manifest, checksum, reason, code, provider=None):
        with self._scope() as session:
            prior = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == request.idempotency_key))
            if prior:
                return self._dto(prior)
            count = session.scalar(select(AssistantMessageModel.message_order).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order.desc()).limit(1)) or 0
            now = datetime.now(UTC)
            if not session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)):
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            user_key = hashlib.sha256(("user:" + request.idempotency_key).encode()).hexdigest()
            user = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == user_key))
            if user is None:
                self._persist_user_message(session, request, conversation_id=conversation_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, message_order=int(count) + 1, now=now, status="completed")
                assistant_order = int(count) + 2
            else:
                user.status = "completed"
                assistant_order = int(count) + 1
            provenance = self._provider_provenance(provider)
            provenance["failure_code"] = code
            row = AssistantMessageModel(id=uuid4().hex, message_id=message_id, conversation_id=conversation_id, run_id=request.run_id, message_order=assistant_order, role="assistant", input_manifest=manifest, input_manifest_checksum=checksum, answer="The Assistant request failed before producing a completed answer.", state_version=int(projection["state_version"]), semantic_state_version=int(projection["state_version"]), operational_event_sequence=int(projection.get("operational_statistics", {}).get("event_sequence", 0) or 0), projection=self._message_projection(projection), evidence=[], proof_label="unknown_or_unavailable", usage=AssistantUsageDto(input_tokens=0, output_tokens=0, total_tokens=0, estimated_input_cost=0, estimated_output_cost=0, estimated_total_cost=0).model_dump(mode="json"), model_provenance=provenance, correlation_id=correlation_id, idempotency_key=request.idempotency_key, request_id=request.request_id, retry_of_message_id=request.retry_of_message_id, intent="unsupported", capability_key="", answer_mode=request.answer_mode, status="failed", failure_reason=reason, created_at=now)
            session.add(row)
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_FAILED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status="failed", idempotency_key=request.idempotency_key, payload={"failure_code": code})
            return self._dto(row, session=session)

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

    @staticmethod
    def _validated_selected_citations(citations: object, selected_refs: list[dict[str, object]], *, proof_label: str) -> list[dict[str, object]] | None:
        """Bind provider citations to the exact immutable excerpts supplied."""
        if not isinstance(citations, list):
            return None
        by_id = {str(item.get("excerpt_id")): item for item in selected_refs if item.get("excerpt_id")}
        validated: list[dict[str, object]] = []
        seen: set[str] = set()
        for citation in citations:
            if not isinstance(citation, dict):
                return None
            excerpt_id = str(citation.get("excerpt_id") or "")
            selected = by_id.get(excerpt_id)
            if selected is None:
                return None
            exact = {
                "excerpt_id": selected.get("excerpt_id"),
                "artifact_id": selected.get("artifact_id"),
                "checksum_sha256": selected.get("checksum_sha256", selected.get("checksum")),
                "stage_key": selected.get("stage_key", selected.get("stage_id") or "run"),
                "locator": selected.get("locator", selected.get("excerpt_locator")),
                "proof_label": selected.get("proof_label", "approved_evidence_supported"),
            }
            if any(citation.get(key) != value for key, value in exact.items()):
                return None
            if exact["proof_label"] != "approved_evidence_supported" or proof_label not in {"approved_evidence_supported", "authoritative_persisted_fact", "model_interpretation"}:
                return None
            if excerpt_id not in seen:
                validated.append(exact)
                seen.add(excerpt_id)
        if proof_label == "approved_evidence_supported" and not validated:
            return None
        return validated

    def answer(self, request: AssistantMessageRequestDto, correlation_id: str | None = None, actor: str = "local-operator") -> AssistantMessageResultDto:
        if not request.run_id:
            raise AssistantRequestError("run_id_required", "A run-scoped assistant request is required.", 422)
        self.authorize(request.run_id, actor)
        request_id = request.request_id or request.idempotency_key or uuid4().hex
        request = request.model_copy(update={"request_id": request_id, "idempotency_key": request.idempotency_key or request_id})
        requested_conversation_id = request.conversation_id
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
                conversation_id = request.conversation_id
            else:
                selected_conversation = session.scalar(select(AssistantConversationModel.conversation_id).where(AssistantConversationModel.run_id == request.run_id).order_by(AssistantConversationModel.updated_at.desc(), AssistantConversationModel.id.desc()).limit(1))
                conversation_id = selected_conversation or uuid4().hex
            request = request.model_copy(update={"conversation_id": conversation_id})
            checksum = self._request_checksum(request)
            history_query = select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.conversation_id == conversation_id)
            history = session.scalars(history_query.order_by(AssistantMessageModel.message_order.desc()).limit(_MAX_HISTORY)).all()
        run = self._run(request.run_id)
        projection = self._projection(run)
        stale = request.client_known_state_version is not None and request.client_known_state_version != projection["state_version"]
        semantic_result = classify_semantic_intent(request.message)
        intent = semantic_result.intent
        capability = self._capabilities.dispatch(semantic_result)
        sanitized_question = _safe_question(request.message)
        history_context = [{"role": item.role, "content": _safe(item.answer, 600)} for item in reversed(history)]
        manifest = {
            "question_sha256": hashlib.sha256(sanitized_question.encode("utf-8")).hexdigest(),
            "question_character_count": len(sanitized_question),
            "projection": projection,
            "history": history_context,
            "intent": intent,
            "capability_key": capability.capability_key if capability else "",
            "configured_input_limit": MAX_INPUT_TOKENS,
        }
        mutation_request = is_mutation_request(request.message) or self._intent(request.message) == "mutation"
        if mutation_request:
            intent = "unsupported"
            capability = None
        if mutation_request and requested_conversation_id is None:
            conversation_id = uuid4().hex
            request = request.model_copy(update={"conversation_id": conversation_id})
            checksum = self._request_checksum(request)
        with self._scope() as session:
            count = session.scalar(select(AssistantMessageModel.message_order).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order.desc()).limit(1)) or 0
            now = datetime.now(UTC)
            if not session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id)):
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            self._persist_user_message(session, request, conversation_id=conversation_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, message_order=int(count) + 1, now=now)
        with self._scope() as session:
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_STARTED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status="started", idempotency_key=request.idempotency_key, payload={"request_id": request.request_id})
        answer, proof = self._compose(intent, projection, sanitized_question)
        answer = _humanize_primary_answer(answer, projection, sanitized_question)
        if mutation_request:
            answer = "This Assistant is read-only and cannot approve gates, execute commands, apply patches, or change workflow state. Use the governed cockpit control for that action."
            proof = "model interpretation"
        governed_response = None
        selected_refs: list[dict[str, object]] = []
        validated_citations: list[dict[str, object]] = []
        evidence: list[AssistantEvidenceDto] = []
        if not mutation_request and capability is not None:
            try:
                with self._scope() as session:
                    evidence_segments, selected_refs = self._evidence_retrieval.retrieve(session, request.run_id, request.message)
                selected_excerpt_ids = [str(ref["excerpt_id"]) for ref in selected_refs if ref.get("excerpt_id")]
                policy = capability.provider_policy(selected_intent=intent, selected_excerpt_ids=selected_excerpt_ids)
                provider_contract = build_assistant_response_contract(intent=intent, capability_key=capability.capability_key, selected_excerpt_ids=selected_excerpt_ids, selected_citations=selected_refs)
                response_contract = build_assistant_response_contract(intent=intent, capability_key=capability.capability_key, selected_excerpt_ids=selected_excerpt_ids, bind_excerpt_ids=False, require_citations=False)
                prepared = prepare_assistant_request(
                    policy=policy,
                    schema=_azure_strict_schema(provider_contract.model_json_schema()),
                    question=sanitized_question,
                    segments=[LlmContextSegment(segment_id="projection", label="current authoritative workflow projection; highest priority", content=json.dumps(projection, sort_keys=True)), *evidence_segments, LlmContextSegment(segment_id="history", label="historical conversation; lower priority than current state and evidence", content=json.dumps(history_context, sort_keys=True))],
                    answer_mode=request.answer_mode,
                )
                manifest["context_budget"] = prepared.manifest.get("context_budget", {})
                supplied_ids = set(prepared.manifest.get("selected_item_ids", []))
                selected_refs = [ref for ref in selected_refs if ref.get("excerpt_id") in supplied_ids]
                manifest["selected_evidence"] = [{key: value for key, value in ref.items() if key not in {"text", "excerpt_locator"}} for ref in selected_refs]
                manifest["evidence_selection"] = self._evidence_retrieval.last_manifest
                with self._scope() as session:
                    self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_CONTEXT_BUILT", correlation_id=correlation_id, state_version=int(projection["state_version"]), status="context_built", idempotency_key=request.idempotency_key, payload={"capability_key": capability.capability_key, "answer_mode": prepared.answer_mode, "final_token_count": prepared.final_input_tokens, "selected_count": len(selected_refs), "omitted_count": len(prepared.manifest.get("omitted_item_ids", [])), "truncated": bool(prepared.manifest.get("truncated_item_ids")), "semantic_state_version": int(projection["state_version"]), "request_manifest_reference": checksum})
                governed_response = self._invocations.assistant(AssistantInvocationRequest(run_id=request.run_id, expected_state_version=int(projection["state_version"]), idempotency_key=f"assistant:{request.request_id}", correlation_id=correlation_id, question=prepared.question, context=list(prepared.context), max_output_tokens=prepared.effective_output_cap, prepared_request=prepared, adaptive_answer_target=prepared.adaptive_answer_target, answer_mode=prepared.answer_mode, response_contract=response_contract), actor=actor)
                if governed_response.status != "completed":
                    raise self._provider_failure(governed_response)
                output = governed_response.structured_output or {}
                if output.get("intent") not in {None, intent} or output.get("capability_key") not in {None, capability.capability_key}:
                    raise AssistantRequestError("assistant_invalid_structured_response", "The governed Assistant returned a response for an unexpected capability.", 502)
                provider_proof = output.get("proof_label", "unknown_or_unavailable")
                citations = output.get("citations", [])
                validated_citations = self._validated_selected_citations(citations, selected_refs, proof_label=provider_proof)
                if validated_citations is None:
                    raise AssistantRequestError("assistant_invalid_citation", "The governed Assistant returned an invalid evidence citation.", 502)
                if isinstance(output.get("answer"), str):
                    answer = _humanize_primary_answer(output["answer"], projection, sanitized_question)
                    proof = provider_proof
                    answer_lower = answer.lower()
                    if intent in {"workflow_status", "blocker_or_failure"} and projection.get("blocker") == "NO_COMPATIBLE_RUNTIME_PROFILE" and ("unknown" in answer_lower or "stale answer" in answer_lower or "execution-profile resolution blocked" not in answer_lower):
                        answer = self._authoritative_workflow_answer(projection)
                        proof = "authoritative_persisted_fact"
                governed_response = governed_response.model_copy(update={"structured_output": {**output, "answer": answer, "proof_label": proof, "citations": validated_citations}})
            except ContextBudgetExceeded:
                failed = self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest={**manifest, "context_budget_failure": "mandatory_content_exceeds_hard_limit"}, checksum=checksum, reason="The Assistant input could not be bounded safely.", code="assistant_context_budget_exceeded")
                raise AssistantRequestError("assistant_context_budget_exceeded", "The Assistant input could not be bounded safely.", 413, correlation_id=correlation_id, details={"message_id": failed.message_id, "conversation_id": failed.conversation_id})
            except AssistantRequestError as error:
                failed = self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, reason=error.message, code=error.code, provider=governed_response)
                error.correlation_id = correlation_id
                error.details = {"message_id": failed.message_id, "conversation_id": failed.conversation_id, "request_id": failed.request_id, "retry_of_message_id": failed.retry_of_message_id}
                raise
            except Exception as error:
                code = getattr(error, "code", "assistant_provider_failed")
                status = getattr(error, "status_code", 503)
                message = "The governed Assistant provider failed; retry is safe."
                failed = self._persist_failed_result(request, conversation_id=conversation_id, message_id=message_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, reason=message, code=code, provider=governed_response)
                raise AssistantRequestError(code, message, status, correlation_id=correlation_id, details={"message_id": failed.message_id, "conversation_id": failed.conversation_id, "request_id": failed.request_id, "retry_of_message_id": failed.retry_of_message_id}) from error
        structured = governed_response.structured_output if governed_response is not None else {
            "answer": answer,
            "summary": answer[:240],
            "intent": "unsupported",
            "capability_key": "",
            "proof_label": "model_interpretation" if mutation_request else proof.replace(" ", "_") if proof else "unknown_or_unavailable",
            "citations": [], "missing_information": [] if not answer.lower().endswith("unavailable.") else ["authoritative information for this question"],
            "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "low" if mutation_request else "medium",
        }
        if governed_response is not None and hasattr(self._invocations, "persist_validated_response"):
            governed_response = self._invocations.persist_validated_response(governed_response, structured)
        if governed_response is not None and structured.get("citations"):
            labels = {str(ref.get("excerpt_id")): str(ref.get("label", ref.get("artifact_id", "evidence"))) for ref in selected_refs}
            evidence = [AssistantEvidenceDto(artifact_id=str(item["artifact_id"]), checksum=str(item["checksum_sha256"]), label=labels.get(str(item["excerpt_id"]), str(item["artifact_id"])), excerpt_id=str(item["excerpt_id"]), checksum_sha256=str(item["checksum_sha256"]), stage_key=str(item["stage_key"]), locator=item["locator"], proof_label=str(item["proof_label"])) for item in structured["citations"]]
        elif governed_response is not None and structured.get("proof_label") == "authoritative_persisted_fact":
            evidence = [AssistantEvidenceDto.model_validate(item) for item in projection["evidence"]]
        elif governed_response is None and not mutation_request:
            evidence = [AssistantEvidenceDto.model_validate(item) for item in projection["evidence"]]
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
            conversation = session.scalar(select(AssistantConversationModel).where(AssistantConversationModel.run_id == request.run_id, AssistantConversationModel.conversation_id == conversation_id))
            if conversation is None:
                session.add(AssistantConversationModel(id=uuid4().hex, conversation_id=conversation_id, run_id=request.run_id, created_at=now, updated_at=now))
            else:
                conversation.updated_at = now
            user_key = hashlib.sha256(("user:" + request.idempotency_key).encode()).hexdigest()
            user = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == request.run_id, AssistantMessageModel.idempotency_key == user_key))
            if user is None:
                self._persist_user_message(session, request, conversation_id=conversation_id, correlation_id=correlation_id, projection=projection, manifest=manifest, checksum=checksum, message_order=int(count) + 1, now=now, status="completed")
                assistant_order = int(count) + 2
            else:
                user.status = "completed"
                assistant_order = int(count) + 1
            provenance = self._provider_provenance(governed_response)
            provenance.update({
                "assistant_v11": {
                    "schema_version": "assistant-response-v1",
                    "validated_response_artifact": {"artifact_id": governed_response.artifact_ids[0], "checksum": governed_response.artifact_checksums[governed_response.artifact_ids[0]]} if governed_response is not None and governed_response.artifact_ids else None,
                    "semantic_classifier": semantic_result.model_dump(mode="json"),
                },
            })
            row = AssistantMessageModel(id=uuid4().hex, message_id=message_id, conversation_id=conversation_id, run_id=request.run_id, message_order=assistant_order, role="assistant", input_manifest=manifest, input_manifest_checksum=checksum, answer=answer, state_version=int(projection["state_version"]), semantic_state_version=int(projection["state_version"]), operational_event_sequence=int(governed_response.event_sequence if governed_response is not None else projection.get("operational_event_sequence", 0) or 0), projection=self._message_projection(projection), evidence=[item.model_dump(mode="json") for item in evidence], proof_label=str(structured.get("proof_label", proof)), usage=usage.model_dump(mode="json"), model_provenance=provenance, correlation_id=correlation_id, idempotency_key=request.idempotency_key, request_id=request.request_id, retry_of_message_id=request.retry_of_message_id, intent=str(structured.get("intent", intent)), capability_key=str(structured.get("capability_key", capability.capability_key if capability else "")), answer_mode=request.answer_mode, status="stale" if stale else "completed", created_at=now)
            session.add(row)
            self._append_event(session, run_id=request.run_id, conversation_id=conversation_id, message_id=message_id, event_type="ASSISTANT_RESPONSE_COMPLETED", correlation_id=correlation_id, state_version=int(projection["state_version"]), status=row.status, idempotency_key=request.idempotency_key, payload={"message_id": message_id})
            return self._dto(row, session=session, stale=stale)

    def history(self, run_id: str, conversation_id: str | None = None, *, actor: str | None = None) -> AssistantHistoryDto:
        self.authorize(run_id, actor or "")
        run = self._run(run_id, with_projection=False)
        if getattr(run, "assistant_projection", None) is not None:
            current_version = int(getattr(run, "state_version", 1) or 1)
        else:
            current_version = int(self._projection(run)["state_version"])
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
            return {}
        try:
            root = Path(run.artifact_root or get_settings().artifact_root)
            store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
            payload = json.loads(store.read_artifact(row.run_id, artifact.relative_path).content)
        except (OSError, TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _dto(row: AssistantMessageModel, *, session=None, stale: bool | None = None) -> AssistantMessageResultDto:
        projection = row.projection
        stats = projection.get("operational_statistics")
        structured = AssistantContextService._structured_response(row, session) if session is not None else {}
        legacy = not structured
        provenance = row.model_provenance or {}
        deployment = provenance.get("deployment")
        model = str(deployment if deployment not in {None, "", "none"} else provenance.get("role") or "deterministic_projection")
        proof = structured.get("proof_label", row.proof_label)
        if proof == "authoritative persisted fact": proof = "authoritative_persisted_fact"
        if proof == "unknown or unavailable": proof = "unknown_or_unavailable"
        intent = structured.get("intent", row.intent)
        if intent not in {"workflow_status", "blocker_or_failure", "completed_work", "remaining_work", "analysis_explanation", "planning_explanation", "transformation_explanation", "validation_explanation", "evidence_question", "usage_and_cost", "next_steps", "comparison", "general_migration_question", "unsupported"}:
            intent = "unsupported"
        answer = structured.get("answer", row.answer)
        if row.role == "assistant":
            if (_RAW_PROJECTION.search(str(answer)) or str(answer).casefold().startswith("current migration context:")) and row.intent == "unsupported":
                paired = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == row.run_id, AssistantMessageModel.conversation_id == row.conversation_id, AssistantMessageModel.role == "user", AssistantMessageModel.message_order < row.message_order).order_by(AssistantMessageModel.message_order.desc()).limit(1)) if session is not None else None
                answer = _GREETING if paired is not None and _is_greeting(paired.answer) else "I can help you understand this migration. Ask me what's happening, what failed, what needs approval, or what changed."
            else:
                answer = _humanize_primary_answer(answer, projection)
        return AssistantMessageResultDto(message_id=row.message_id, model=model, message_order=row.message_order, conversation_id=row.conversation_id, run_id=row.run_id, role=row.role, answer=answer, current_phase=str(projection.get("phase", "unknown")), current_stage=str(projection.get("stage", "unknown")), workflow_status=str(projection.get("status", "unknown")), current_gate=str(projection.get("gate", "unknown")), current_blocker=str(projection.get("blocker", "unknown")), next_permitted_action=str(projection.get("next_action", "unknown")), workflow_state_version=row.state_version, stale=stale if stale is not None else row.status == "stale", evidence_references=[AssistantEvidenceDto.model_validate(item) for item in row.evidence], proof_label=proof, usage=AssistantUsageDto.model_validate(row.usage), response_status=row.status, failure_reason=row.failure_reason, error_code=provenance.get("failure_code"), operational_statistics=AssistantOperationalStatisticsDto.model_validate(stats) if stats else None, request_id=row.request_id, retry_of_message_id=row.retry_of_message_id, intent=intent, capability_key=structured.get("capability_key", row.capability_key if not legacy else ""), summary=structured.get("summary", "unavailable" if legacy else str(answer)[:240]), citations=structured.get("citations", []), missing_information=structured.get("missing_information", ["V1.1 metadata unavailable for this legacy message"] if legacy else []), suggested_follow_ups=structured.get("suggested_follow_ups", []), next_step_proposals=projection.get("next_step_proposals", structured.get("next_step_proposals", [])), confidence=structured.get("confidence", "unknown_or_unavailable"), correlation_id=row.correlation_id, semantic_state_version=row.semantic_state_version, operational_event_sequence=row.operational_event_sequence, answer_mode=row.answer_mode)
