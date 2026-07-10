"""Repository adapter for persisted migration-run records."""

from sqlalchemy.orm import Session

from app.repositories.models import MigrationRunModel


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