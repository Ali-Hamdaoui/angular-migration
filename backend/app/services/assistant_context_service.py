"""Assistant context service for G08 S4-F11.

Provides read-only evidence-grounded migration state explanation through the AI Assistant.
Selects authoritative state, constructs sanitized bounded prompts, and records usage/cost.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field
from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, RunStatus, WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    AssistantConversationModel,
    AssistantMessageModel,
    LlmInvocationModel,
    LlmUsageRecordModel,
    MigrationRunModel,
    UsageCostRecordModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope


class AssistantError(ValueError):
    """Stable domain error raised when the assistant cannot process a request."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AssistantMessageRequest:
    run_id: str
    actor: str
    message: str
    idempotency_key: str
    expected_state_version: int = 1
    suggested_questions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssistantMessageResult:
    response: str
    status: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    conversation_id: str
    artifact_refs: tuple[ArtifactRefDto, ...]
    deterministic_fallback: bool = False


@dataclass(frozen=True)
class ConversationInfo:
    conversation_id: str
    run_id: str
    actor: str
    message_count: int
    total_tokens_used: int
    total_cost_usd: float
    created_at: datetime
    updated_at: datetime


class AssistantContextService:
    """Read-only assistant that explains authoritative migration state.

    Never executes commands, approves decisions, or mutates workflow state.
    """

    # Assistant forbidden-action categories for the LLM prompt
    FORBIDDEN_ACTIONS = [
        "command execution",
        "file mutation",
        "state transition",
        "gate approval",
        "secret exposure",
        "raw path disclosure",
    ]

    def __init__(self, settings, *, session_scope_factory=session_scope, now_provider=None, artifact_store=None) -> None:
        self._settings = settings
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._artifact_store = artifact_store

    def send_message(self, request: AssistantMessageRequest) -> AssistantMessageResult:
        with self._scope() as session:
            # Verify run exists
            run = session.get(MigrationRunModel, request.run_id)
            if run is None:
                raise AssistantError("RUN_NOT_FOUND", "Migration run does not exist.")

            # Get or create conversation
            conv = session.scalar(
                select(AssistantConversationModel).where(
                    AssistantConversationModel.run_id == request.run_id,
                    AssistantConversationModel.actor == request.actor,
                )
            )
            if conv is None:
                conv = AssistantConversationModel(
                    id=f"conv-{uuid4().hex[:12]}",
                    run_id=request.run_id,
                    actor=request.actor,
                    created_at=self._now(),
                    updated_at=self._now(),
                    state_version=1,
                )
                session.add(conv)
                session.flush()

            # Build evidence context — authoritative state only
            state_context = self._build_authoritative_context(session, request.run_id)

            # LLM invocation (deterministic fallback if no real LLM)
            now = self._now()
            is_fallback = True  # Deterministic fallback for initial implementation

            if is_fallback:
                response = self._deterministic_response(state_context, request.message, request.suggested_questions)
                input_tokens = 0
                output_tokens = 0
                cost_usd = 0.0
            else:
                # Real LLM path would go through the gateway here
                response = "LLM gateway not configured; using fallback explanation."
                input_tokens = 0
                output_tokens = 0
                cost_usd = 0.0

            # Persist message metadata (no hidden chain-of-thought)
            msg = AssistantMessageModel(
                id=f"msg-{uuid4().hex[:12]}",
                conversation_id=conv.id,
                run_id=request.run_id,
                role="user",
                content_summary=f"Q: {request.message[:200]}",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                created_at=now,
            )
            session.add(msg)

            resp_msg = AssistantMessageModel(
                id=f"msg-{uuid4().hex[:12]}",
                conversation_id=conv.id,
                run_id=request.run_id,
                role="assistant",
                content_summary=f"A: {response[:200]}",
                artifact_refs=[],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                created_at=now,
            )
            session.add(resp_msg)

            # Update conversation metadata
            conv.message_count += 2
            conv.total_tokens_used += input_tokens + output_tokens
            conv.total_cost_usd += cost_usd
            conv.updated_at = now

            # Create evidence artifacts
            evidence = {
                "assistant_input_manifest.json": self._build_input_manifest(request, state_context),
                "assistant_structured_answer.json": {
                    "run_id": request.run_id,
                    "question": request.message,
                    "answer": response,
                    "deterministic_fallback": is_fallback,
                    "evidence_citations": state_context.get("evidence_citations", []),
                },
                "assistant_usage_record.json": {
                    "run_id": request.run_id,
                    "conversation_id": conv.id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost_usd,
                    "deterministic_fallback": is_fallback,
                },
            }
            store = self._artifact_store or LocalFilesystemArtifactStore(self._settings.artifact_root)
            store.ensure_run_layout(request.run_id)

            artifact_refs: list[ArtifactRefDto] = []
            for name, payload in evidence.items():
                stored = store.write_text_artifact(
                    request.run_id, f"assistant/{name}",
                    json.dumps(payload, sort_keys=True, indent=2),
                    ArtifactType.JSON,
                    created_by="assistant-context-service",
                    created_at=now,
                    input_hashes={"idempotency_key": request.idempotency_key},
                    policy_version="g08-s4-f11-v1",
                )
                artifact_refs.append(stored.ref)
                session.add(
                    ArtifactMetadataModel(
                        id=f"metadata-{stored.ref.artifact_id}",
                        run_id=request.run_id,
                        stage_id=None,
                        artifact_type=stored.ref.artifact_type.value,
                        relative_path=stored.ref.relative_path,
                        checksum=stored.ref.checksum,
                        created_at=now,
                    )
                )

            # Calculate event sequence from DB
            latest_sequence = session.scalar(
                select(WorkflowEventModel.sequence)
                .where(WorkflowEventModel.run_id == request.run_id)
                .order_by(WorkflowEventModel.sequence.desc()).limit(1)
            )
            next_sequence = (latest_sequence or 0) + 1

            # Emit ASSISTANT_RESPONSE_COMPLETED event
            event = WorkflowEventModel(
                id=f"event-{uuid4().hex[:12]}",
                run_id=request.run_id,
                event_type=WorkflowEventType.ASSISTANT_RESPONSE_COMPLETED.value,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                reason="assistant response completed",
                sequence=next_sequence,
                payload={
                    "conversation_id": conv.id,
                    "message_count": conv.message_count,
                    "total_tokens_used": conv.total_tokens_used,
                    "total_cost_usd": conv.total_cost_usd,
                    "deterministic_fallback": is_fallback,
                    "artifact_ids": [r.artifact_id for r in artifact_refs],
                },
                occurred_at=now,
            )
            session.add(event)
            session.flush()

            return AssistantMessageResult(
                response=response,
                status="completed",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                conversation_id=conv.id,
                artifact_refs=tuple(artifact_refs),
                deterministic_fallback=is_fallback,
            )

    def get_conversation(self, run_id: str, actor: str) -> ConversationInfo | None:
        with self._scope() as session:
            conv = session.scalar(
                select(AssistantConversationModel).where(
                    AssistantConversationModel.run_id == run_id,
                    AssistantConversationModel.actor == actor,
                )
            )
            if conv is None:
                return None
            return ConversationInfo(
                conversation_id=conv.id,
                run_id=conv.run_id,
                actor=conv.actor,
                message_count=conv.message_count,
                total_tokens_used=conv.total_tokens_used,
                total_cost_usd=conv.total_cost_usd,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )

    def _build_authoritative_context(self, session, run_id: str) -> dict:
        """Collect authoritative state and approved artifacts for the assistant."""
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            return {"error": "run not found"}

        # Get recent events
        events = list(
            session.scalars(
                select(WorkflowEventModel)
                .where(WorkflowEventModel.run_id == run_id)
                .order_by(WorkflowEventModel.sequence.desc())
                .limit(20)
            )
        )

        # Get artifacts
        artifacts = list(
            session.scalars(
                select(ArtifactMetadataModel)
                .where(ArtifactMetadataModel.run_id == run_id)
                .limit(50)
            )
        )

        return {
            "run_id": run.id,
            "status": run.status,
            "run_phase": run.run_phase,
            "phase_status": run.phase_status,
            "approval_status": run.approval_status,
            "repair_status": run.repair_status,
            "state_version": run.state_version,
            "source_version_family": run.source_version_family,
            "target_version_family": run.target_version_family,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "recent_events": [
                {"event_type": e.event_type, "occurred_at": e.occurred_at.isoformat(), "reason": e.reason}
                for e in events
            ],
            "evidence_citations": [
                {"artifact_id": a.id, "artifact_type": a.artifact_type, "checksum": a.checksum}
                for a in artifacts
            ],
            "forbidden_actions": self.FORBIDDEN_ACTIONS,
        }

    def _deterministic_response(self, context: dict, question: str, suggested: list[str]) -> str:
        """Produce a deterministic read-only fallback explanation."""
        status = context.get("status", "unknown")
        phase = context.get("run_phase", "unknown")
        phase_status = context.get("phase_status", "unknown")
        events = context.get("recent_events", [])
        citations = context.get("evidence_citations", [])

        lines = [
            f"**Run Status:** {status}",
            f"**Phase:** {phase} ({phase_status})",
            f"**Evidence Available:** {len(citations)} artifacts",
            f"**Recent Events:** {len(events)}",
            "",
            "This is a deterministic fallback explanation (LLM gateway not configured).",
            "",
            "**Available context:**",
        ]
        for ev in events[:5]:
            lines.append(f"- {ev['event_type']} ({ev.get('reason', '')})")

        if citations:
            lines.append("")
            lines.append("**Evidence citations:**")
            for c in citations[:5]:
                lines.append(f"- {c['artifact_type']}: {c['artifact_id']}")

        lines.append("")
        lines.append("**Forbidden actions in this context:**")
        for action in self.FORBIDDEN_ACTIONS:
            lines.append(f"- {action}")

        if suggested:
            lines.append("")
            lines.append("**Suggested questions:**")
            for q in suggested:
                lines.append(f"- {q}")

        return "\n".join(lines)

    def _build_input_manifest(self, request: AssistantMessageRequest, context: dict) -> dict:
        """Build sanitized assistant input manifest artifact."""
        return {
            "run_id": request.run_id,
            "actor": request.actor,
            "question": request.message,
            "context_summary": {
                "status": context.get("status"),
                "phase": context.get("run_phase"),
                "event_count": len(context.get("recent_events", [])),
                "evidence_count": len(context.get("evidence_citations", [])),
            },
            "bounded_context_size": len(json.dumps(context, sort_keys=True)),
            "forbidden_actions": self.FORBIDDEN_ACTIONS,
        }
