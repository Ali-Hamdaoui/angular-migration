"""Log streaming service for G01 S3-F03.

Provides bounded log chunk publishing, stored log retrieval,
and reconnect-safe state for the frontend log viewer.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import WorkflowEventType
from app.repositories.models.workflow import (
    CommandExecutionModel,
    CommandLogChunkModel,
    CommandLogSummaryModel,
    WorkflowEventModel,
)


# Maximum log chunks to keep in memory per execution
MAX_LIVE_CHUNKS = 10000
MAX_CHUNK_BYTES = 64_000
MAX_EXECUTION_BYTES = 10_000_000
_SEQUENCE_LOCKS: dict[str, threading.Lock] = {}
_SEQUENCE_LOCKS_GUARD = threading.Lock()
_REDACTION_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)((?:api[_-]?key|x-api-key|subscription-key)\s*[:=]\s*)[^\s,;]{8,}"),
    re.compile(r"(?im)^([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PRIVATE[_-]?KEY)[A-Z0-9_]*\s*=\s*).+$"),
    re.compile(r"(?i)((?:AccountKey|SharedAccessKey|Password)=)[^;\s]+"),
    re.compile(r"(?i)(_authToken\s*=\s*)[A-Za-z0-9._~+/=-]{8,}"),
)


@dataclass(frozen=True)
class LogChunkDto:
    """One log chunk in the ordered stream."""
    sequence: int
    stream: str  # stdout, stderr, system
    text: str
    redacted: bool = False
    created_at: str = ""
    byte_count: int = 0
    character_count: int = 0
    truncated: bool = False


class CommandLogService:
    """Service for live log streaming and stored log retrieval."""

    def append_chunk(
        self,
        session: Session,
        execution_id: str,
        run_id: str,
        stream: str,
        text: str,
        *,
        redacted: bool = False,
        correlation_id: str | None = None,
        max_chunk_bytes: int = MAX_CHUNK_BYTES,
        max_execution_bytes: int = MAX_EXECUTION_BYTES,
        strict_ownership: bool = False,
    ) -> CommandLogChunkModel:
        """Append a UTF-8-safe bounded chunk with one execution-wide sequence.

        The process reader supplies bytes decoded with ``errors='replace'``.
        A process-local execution lock serializes stdout/stderr writers; the
        database uniqueness constraint is the final replay/concurrency guard.
        Availability is emitted on the first chunk and every tenth chunk.
        """
        if stream not in {"stdout", "stderr", "system"}:
            raise ValueError("INVALID_LOG_STREAM")
        if strict_ownership:
            execution = session.get(CommandExecutionModel, execution_id)
            if execution is None or execution.run_id != run_id:
                raise ValueError("LOG_EXECUTION_RUN_MISMATCH")
            if execution.status in {"succeeded", "failed", "cancelled", "timed_out"}:
                raise ValueError("LOG_EXECUTION_FINALIZED")
        safe_text, changed = self.redact_text(text)
        encoded = safe_text.encode("utf-8")
        truncated = len(encoded) > max_chunk_bytes
        if truncated:
            safe_text = encoded[:max_chunk_bytes].decode("utf-8", errors="replace")
            safe_text += "\n[log chunk truncated]"
        with _SEQUENCE_LOCKS_GUARD:
            lock = _SEQUENCE_LOCKS.setdefault(execution_id, threading.Lock())
        with lock:
            summary = session.get(CommandLogSummaryModel, execution_id)
            if summary is None:
                summary = CommandLogSummaryModel(execution_id=execution_id, run_id=run_id, correlation_id=correlation_id)
                session.add(summary)
                session.flush()
            current_bytes = summary.stdout_stored_bytes + summary.stderr_stored_bytes
            available = max(0, max_execution_bytes - current_bytes)
            if len(safe_text.encode("utf-8")) > available:
                safe_text = safe_text.encode("utf-8")[:available].decode("utf-8", errors="replace")
                truncated = True
            latest = session.scalar(select(CommandLogChunkModel).where(CommandLogChunkModel.execution_id == execution_id).order_by(CommandLogChunkModel.sequence.desc()).limit(1))
            next_seq = (latest.sequence + 1) if latest else 1
            now = datetime.now(UTC)
            chunk = CommandLogChunkModel(id=f"chunk-{uuid4().hex[:12]}", execution_id=execution_id, run_id=run_id, sequence=next_seq, stream=stream, text=safe_text, redacted=redacted or changed, created_at=now)
            session.add(chunk)
            summary.first_sequence = summary.first_sequence or next_seq
            summary.last_sequence = next_seq
            count_field = "stdout_chunk_count" if stream == "stdout" else "stderr_chunk_count"
            bytes_field = "stdout_stored_bytes" if stream == "stdout" else "stderr_stored_bytes"
            setattr(summary, count_field, getattr(summary, count_field) + 1)
            setattr(summary, bytes_field, getattr(summary, bytes_field) + len(safe_text.encode("utf-8")))
            if truncated:
                setattr(summary, f"{stream}_truncated", True)
            summary.redaction_applied = summary.redaction_applied or redacted or changed
            session.flush()

        # Emit bounded lightweight availability events, never content.
        if next_seq == 1 or next_seq % 10 == 0:
            latest_event = session.scalar(
                select(WorkflowEventModel)
                .where(WorkflowEventModel.run_id == run_id)
                .order_by(WorkflowEventModel.sequence.desc())
                .limit(1)
            )
            event = WorkflowEventModel(
                id=f"event-{uuid4().hex[:12]}",
                run_id=run_id,
                stage_id=None,
                event_type=WorkflowEventType.COMMAND_OUTPUT_AVAILABLE.value,
                idempotency_key=f"log-{execution_id}-{next_seq}",
                actor="command-executor",
                reason=f"log chunk #{next_seq} ({stream})",
                sequence=(latest_event.sequence + 1) if latest_event else 1,
                payload={
                    "execution_id": execution_id,
                    "first_sequence": next_seq,
                    "latest_sequence": next_seq,
                    "stream": stream,
                    "chunk_id": chunk.id,
                    "correlation_id": correlation_id,
                },
                occurred_at=now,
            )
            session.add(event)
        return chunk

    def ensure_summary(self, session: Session, execution_id: str, run_id: str, *, correlation_id: str | None = None) -> CommandLogSummaryModel:
        summary = session.get(CommandLogSummaryModel, execution_id)
        if summary is None:
            summary = CommandLogSummaryModel(execution_id=execution_id, run_id=run_id, correlation_id=correlation_id)
            session.add(summary)
            session.flush()
        return summary

    @staticmethod
    def redact_text(text: str) -> tuple[str, bool]:
        changed = False
        for pattern in _REDACTION_PATTERNS:
            text, count = pattern.subn(lambda match: f"{match.group(1)}[REDACTED]", text)
            changed = changed or bool(count)
        return text, changed

    def finalize(self, session: Session, execution_id: str, *, finalized_at: datetime | None = None) -> dict[str, Any]:
        summary = session.get(CommandLogSummaryModel, execution_id)
        if summary is None:
            raise ValueError("LOG_EXECUTION_NOT_FOUND")
        summary.finalized = True
        summary.finalized_at = finalized_at or datetime.now(UTC)
        session.flush()
        return self.get_stream_summary(session, execution_id)

    def get_logs(
        self,
        session: Session,
        execution_id: str,
        *,
        offset: int = 0,
        limit: int = 1000,
        stream_filter: str | None = None,
        cursor: int | None = None,
    ) -> tuple[list[LogChunkDto], int]:
        """Retrieve stored log chunks for a command execution.

        Args:
            session: DB session
            execution_id: Target execution ID
            offset: Row offset for pagination (used when cursor is None)
            limit: Max rows to return
            stream_filter: Optional stream name filter (stdout, stderr, system)
            cursor: If set, return only chunks with sequence > cursor
                    (overrides offset for cursor-based pagination)
        """
        base_query = select(CommandLogChunkModel).where(
            CommandLogChunkModel.execution_id == execution_id
        )

        if stream_filter:
            base_query = base_query.where(CommandLogChunkModel.stream == stream_filter)

        if cursor is not None:
            base_query = base_query.where(CommandLogChunkModel.sequence > cursor)

        # Get total count
        count_query = select(CommandLogChunkModel).where(
            CommandLogChunkModel.execution_id == execution_id
        )
        if stream_filter:
            count_query = count_query.where(CommandLogChunkModel.stream == stream_filter)
        total = len(list(session.scalars(count_query.with_only_columns(CommandLogChunkModel.sequence))))

        chunks = list(
            session.scalars(
                base_query.order_by(CommandLogChunkModel.sequence)
                .offset(offset if cursor is None else 0)
                .limit(limit)
            )
        )
        return [
            LogChunkDto(
                sequence=c.sequence,
                stream=c.stream,
                text=c.text,
                redacted=c.redacted,
                created_at=c.created_at.isoformat() if c.created_at else "",
                byte_count=len(c.text.encode("utf-8")),
                character_count=len(c.text),
            )
            for c in chunks
        ], total

    def get_stream_summary(
        self,
        session: Session,
        execution_id: str,
    ) -> dict[str, Any]:
        """Get a summary of available log streams."""
        rows = session.scalars(
            select(CommandLogChunkModel)
            .where(CommandLogChunkModel.execution_id == execution_id)
        ).all()
        total = len(rows)
        stdout_count = sum(1 for r in rows if r.stream == "stdout")
        stderr_count = sum(1 for r in rows if r.stream == "stderr")
        system_count = sum(1 for r in rows if r.stream == "system")

        summary = session.get(CommandLogSummaryModel, execution_id)
        return {
            "execution_id": execution_id,
            "total_chunks": total,
            "streams": {
                "stdout": stdout_count,
                "stderr": stderr_count,
                "system": system_count,
            },
            "first_sequence": summary.first_sequence if summary else None,
            "last_sequence": summary.last_sequence if summary else None,
            "finalized": bool(summary.finalized) if summary else False,
            "finalized_at": summary.finalized_at.isoformat() if summary and summary.finalized_at else None,
            "truncated": {"stdout": bool(summary.stdout_truncated) if summary else False, "stderr": bool(summary.stderr_truncated) if summary else False},
            "redaction_applied": bool(summary.redaction_applied) if summary else False,
        }
