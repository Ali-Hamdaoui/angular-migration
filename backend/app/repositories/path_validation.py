"""Persistence access for path validation snapshots and reservations."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.path_validation import PathValidationResult
from app.repositories.models import PathValidationModel, TargetReservationModel


class PathValidationRepository:
    def get_by_idempotency(self, session: Session, key: str) -> PathValidationModel | None:
        return session.scalar(select(PathValidationModel).where(PathValidationModel.idempotency_key == key))

    def get_by_id(self, session: Session, validation_id: str) -> PathValidationModel | None:
        return session.get(PathValidationModel, validation_id)

    def save(self, session: Session, result: PathValidationResult, *, key: str, actor: str | None, now: datetime) -> PathValidationModel:
        snapshot = result.snapshot
        record = PathValidationModel(
            id=snapshot.validation_id,
            idempotency_key=key,
            actor=actor,
            status=snapshot.status,
            source_fingerprint=snapshot.source_fingerprint,
            checksum=snapshot.checksum,
            snapshot=snapshot.model_dump(mode="json"),
            created_at=now,
        )
        session.add(record)
        if snapshot.target_reservation_eligible:
            session.add(TargetReservationModel(
                id=f"reservation-{uuid4().hex[:12]}",
                validation_id=snapshot.validation_id,
                target_path=snapshot.target_output_path,
                status="eligible",
                expires_at=now + timedelta(minutes=15),
                created_at=now,
            ))
        session.flush()
        return record

    @staticmethod
    def to_result(record: PathValidationModel) -> PathValidationResult:
        from app.domain.path_validation import PathValidationSnapshot

        return PathValidationResult(snapshot=PathValidationSnapshot.model_validate(record.snapshot))