"""Repository adapter for persisted migration-run records."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.repositories.models import CommandExecutionModel, MigrationRunModel, WorkflowEventModel


class StaleStateVersionError(RuntimeError):
    """Raised when optimistic concurrency rejects a run update."""


class MigrationRunRepository:
    """Persistence-only operations; workflow rules remain in services later."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, migration_run: MigrationRunModel) -> MigrationRunModel:
        self._session.add(migration_run)
        self._session.flush()
        return migration_run

    def get_by_id(self, run_id: str) -> MigrationRunModel | None:
        return self._session.get(MigrationRunModel, run_id)

    def update_status_with_version(
        self,
        *,
        run_id: str,
        expected_state_version: int,
        status: str,
        run_phase: str,
        updated_at: datetime,
        phase_status: str = "running",
        approval_status: str = "not_required",
        repair_status: str = "not_required",
    ) -> MigrationRunModel:
        result = self._session.execute(
            update(MigrationRunModel)
            .where(MigrationRunModel.id == run_id)
            .where(MigrationRunModel.state_version == expected_state_version)
            .values(
                status=status,
                run_phase=run_phase,
                phase_status=phase_status,
                approval_status=approval_status,
                repair_status=repair_status,
                state_version=MigrationRunModel.state_version + 1,
                updated_at=updated_at,
            )
        )
        if result.rowcount != 1:
            raise StaleStateVersionError(
                f"run {run_id} is not at expected state version {expected_state_version}"
            )
        self._session.flush()
        persisted = self.get_by_id(run_id)
        if persisted is None:
            raise StaleStateVersionError(f"run {run_id} does not exist")
        return persisted

    def append_event(
        self,
        *,
        event_id: str,
        run_id: str,
        event_type: str,
        occurred_at: datetime,
        stage_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> WorkflowEventModel:
        latest_sequence = self._session.scalar(
            select(func.max(WorkflowEventModel.sequence)).where(WorkflowEventModel.run_id == run_id)
        )
        event = WorkflowEventModel(
            id=event_id,
            run_id=run_id,
            stage_id=stage_id,
            event_type=event_type,
            sequence=(latest_sequence or 0) + 1,
            payload=payload or {},
            occurred_at=occurred_at,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def add_command_execution(self, command_execution: CommandExecutionModel) -> CommandExecutionModel:
        self._session.add(command_execution)
        self._session.flush()
        return command_execution
