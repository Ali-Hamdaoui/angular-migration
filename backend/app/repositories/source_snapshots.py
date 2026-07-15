"""Persistence access for run-scoped source snapshots."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import SourceSnapshotModel


class SourceSnapshotRepository:
    def get_by_id(self, session: Session, snapshot_id: str) -> SourceSnapshotModel | None:
        return session.get(SourceSnapshotModel, snapshot_id)

    def get_by_idempotency(
        self, session: Session, run_id: str, idempotency_key: str
    ) -> SourceSnapshotModel | None:
        return session.scalar(
            select(SourceSnapshotModel)
            .where(SourceSnapshotModel.run_id == run_id)
            .where(SourceSnapshotModel.idempotency_key == idempotency_key)
        )

    def get_latest(self, session: Session, run_id: str) -> SourceSnapshotModel | None:
        return session.scalar(
            select(SourceSnapshotModel)
            .where(SourceSnapshotModel.run_id == run_id)
            .order_by(SourceSnapshotModel.created_at.desc())
        )
