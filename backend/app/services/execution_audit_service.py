"""Immutable execution audit trail service (V2 F27-03).

The audit trail is append-only: entries are never updated or deleted.  Every
entry is bound to the previous entry's checksum so tampering breaks the chain
and is detectable by ``verify_trail``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.domain.command import CommandClass, command_class_for
from app.domain.execution_audit import ExecutionAuditEntry, ExecutionAuditEvent
from app.repositories.execution_audit_models import CommandExecutionAuditModel
from app.repositories.models import MigrationRunModel
from app.repositories.session import session_scope


class ExecutionAuditError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ExecutionAuditTrailService:
    """Append-only execution audit trail (F27-03)."""

    GENESIS = "GENESIS"

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def append(
        self,
        *,
        run_id: str,
        event: ExecutionAuditEvent | str,
        command_id: str,
        stage_id: str | None = None,
        execution_id: str | None = None,
        actor: str | None = None,
        executable: str = "",
        arguments: Sequence[str] = (),
        policy_version: str = "",
        state_version: int | None = None,
        network_profile: str | None = None,
        reason: str = "",
        occurred_at: datetime | None = None,
        session=None,
    ) -> ExecutionAuditEntry:
        """Append one immutable entry bound to the last entry's checksum.

        When ``session`` is supplied the entry is written in that session's
        transaction (no commit); otherwise a dedicated session is opened and
        committed.
        """
        event = ExecutionAuditEvent(event)
        occurred_at = occurred_at or self._now_provider()

        def _write(session) -> ExecutionAuditEntry:
            if session.get(MigrationRunModel, run_id) is None:
                raise ExecutionAuditError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            last = session.scalar(
                select(CommandExecutionAuditModel)
                .where(CommandExecutionAuditModel.run_id == run_id)
                .order_by(CommandExecutionAuditModel.occurred_at.desc(), CommandExecutionAuditModel.id.desc())
                .limit(1)
            )
            prev_checksum = last.checksum if last is not None else self.GENESIS
            entry = ExecutionAuditEntry(
                entry_id="audit-"
                + hashlib.sha256(
                    f"{run_id}:{execution_id or ''}:{occurred_at.isoformat()}:{event.value}".encode()
                ).hexdigest()[:24],
                run_id=run_id,
                stage_id=stage_id,
                execution_id=execution_id,
                command_id=command_id,
                command_class=command_class_for(command_id).value,
                event=event,
                actor=actor,
                executable=executable,
                arguments=tuple(arguments),
                policy_version=policy_version,
                state_version=state_version,
                network_profile=network_profile,
                reason=reason,
                occurred_at=occurred_at,
            ).bind_checksum(prev_checksum)
            session.add(
                CommandExecutionAuditModel(
                    id=entry.entry_id,
                    run_id=run_id,
                    stage_id=stage_id,
                    execution_id=execution_id,
                    command_id=command_id,
                    command_class=entry.command_class,
                    event=entry.event.value,
                    actor=actor,
                    executable=executable,
                    arguments=list(arguments),
                    policy_version=policy_version,
                    state_version=state_version,
                    network_profile=network_profile,
                    reason=reason,
                    prev_checksum=prev_checksum,
                    checksum=entry.checksum,
                    occurred_at=occurred_at,
                )
            )
            session.flush()
            return entry

        if session is not None:
            return _write(session)
        with self._session_scope() as owned:
            entry = _write(owned)
            owned.commit()
            return entry

    def verify_trail(self, run_id: str) -> dict:
        """Recompute the chain and confirm every entry is unbroken."""
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise ExecutionAuditError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            rows = list(
                session.scalars(
                    select(CommandExecutionAuditModel)
                    .where(CommandExecutionAuditModel.run_id == run_id)
                    .order_by(CommandExecutionAuditModel.occurred_at.asc(), CommandExecutionAuditModel.id.asc())
                ).all()
            )
        expected_prev = self.GENESIS
        verified = 0
        first_broken: str | None = None
        for row in rows:
            canonical = {
                "entry_id": row.id,
                "run_id": row.run_id,
                "stage_id": row.stage_id,
                "execution_id": row.execution_id,
                "command_id": row.command_id,
                "command_class": row.command_class,
                "event": row.event,
                "actor": row.actor,
                "executable": row.executable,
                "arguments": list(row.arguments or []),
                "policy_version": row.policy_version,
                "state_version": row.state_version,
                "network_profile": row.network_profile,
                "reason": row.reason,
                "occurred_at": (row.occurred_at.astimezone(UTC).replace(tzinfo=None).isoformat()
                                if row.occurred_at is not None and row.occurred_at.tzinfo is not None
                                else (row.occurred_at.isoformat() if row.occurred_at is not None else None)),
            }
            canonical["prev_checksum"] = row.prev_checksum
            digest = "sha256:" + hashlib.sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if row.prev_checksum != expected_prev or digest != row.checksum:
                if first_broken is None:
                    first_broken = row.id
            else:
                verified += 1
            expected_prev = row.checksum
        return {
            "run_id": run_id,
            "entries": len(rows),
            "verified": verified,
            "intact": len(rows) == verified,
            "first_broken_entry": first_broken,
            "tail_checksum": expected_prev,
        }

    def list_entries(self, run_id: str) -> list[CommandExecutionAuditModel]:
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise ExecutionAuditError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            return list(
                session.scalars(
                    select(CommandExecutionAuditModel)
                    .where(CommandExecutionAuditModel.run_id == run_id)
                    .order_by(CommandExecutionAuditModel.occurred_at.asc(), CommandExecutionAuditModel.id.asc())
                ).all()
            )

    def assert_command_governed(self, command_id: str) -> CommandClass:
        """F27-01 fail-closed: ungoverned commands may never execute."""
        command_class = command_class_for(command_id)
        if command_class is CommandClass.UNGOVERNED:
            raise ExecutionAuditError(
                "COMMAND_CLASS_UNGOVERNED",
                f"command_id '{command_id}' has no governed V2 command class",
            )
        return command_class
