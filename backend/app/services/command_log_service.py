"""Log streaming service for G01 S3-F03.

Provides bounded log chunk publishing, stored log retrieval,
and reconnect-safe state for the frontend log viewer.
"""

from __future__ import annotations

import json
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
    WorkflowEventModel,
)


# Maximum log chunks to keep in memory per execution
MAX_LIVE_CHUNKS = 10000


@dataclass(frozen=True)
class LogChunkDto:
    """One log chunk in the ordered stream."""
    sequence: int
    stream: str  # stdout, stderr, system
    text: str
    redacted: bool = False
    created_at: str = ""


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
    ) -> CommandLogChunkModel:
        """Append one ordered log chunk."""
        latest = session.scalar(
            select(CommandLogChunkModel)
            .where(CommandLogChunkModel.execution_id == execution_id)
            .order_by(CommandLogChunkModel.sequence.desc())
            .limit(1)
        )
        next_seq = (latest.sequence + 1) if latest else 1
        now = datetime.now(UTC)
        chunk = CommandLogChunkModel(
            id=f"chunk-{uuid4().hex[:12]}",
            execution_id=execution_id,
            run_id=run_id,
            sequence=next_seq,
            stream=stream,
            text=text,
            redacted=redacted,
            created_at=now,
        )
        session.add(chunk)

        # Emit COMMAND_OUTPUT_AVAILABLE event
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
                "sequence": next_seq,
                "stream": stream,
                "chunk_id": chunk.id,
            },
            occurred_at=now,
        )
        session.add(event)
        return chunk

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

        return {
            "execution_id": execution_id,
            "total_chunks": total,
            "streams": {
                "stdout": stdout_count,
                "stderr": stderr_count,
                "system": system_count,
            },
        }
