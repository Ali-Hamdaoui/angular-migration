"""Persistence access for path-validation snapshots and exact output-root reservations."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.path_validation import PathValidationResult
from app.repositories.models import PathValidationModel, TargetReservationModel


class PathValidationRepository:
    reservation_ttl = timedelta(minutes=15)

    def get_by_idempotency(self, session: Session, key: str) -> PathValidationModel | None:
        return session.scalar(select(PathValidationModel).where(PathValidationModel.idempotency_key == key))

    def get_by_id(self, session: Session, validation_id: str) -> PathValidationModel | None:
        return session.get(PathValidationModel, validation_id)

    def save(self, session: Session, result: PathValidationResult, *, key: str, actor: str | None, now: datetime) -> PathValidationModel:
        snapshot = result.snapshot
        reservation = None
        if snapshot.target_reservation_eligible:
            existing = session.scalar(select(TargetReservationModel).where(TargetReservationModel.target_path == snapshot.resolved_output_root).order_by(TargetReservationModel.created_at.desc()))
            if existing and self._utc(existing.expires_at) > now:
                snapshot = snapshot.model_copy(update={"status": "blocked", "blockers": sorted(set(snapshot.blockers + ["OUTPUT_ROOT_ALREADY_RESERVED"])), "target_reservation_eligible": False})
            else:
                if existing:
                    existing.status = "expired"
                reservation = TargetReservationModel(id=f"reservation-{uuid4().hex[:12]}", validation_id=snapshot.validation_id, target_path=snapshot.resolved_output_root, status="reserved", expires_at=now + self.reservation_ttl, created_at=now)
                session.add(reservation)
                snapshot = snapshot.model_copy(update={"reservation_id": reservation.id, "reservation_expires_at": reservation.expires_at})
        record = PathValidationModel(id=snapshot.validation_id, idempotency_key=key, actor=actor, status=snapshot.status, source_fingerprint=snapshot.source_fingerprint, checksum=snapshot.checksum, snapshot=snapshot.model_dump(mode="json"), created_at=now)
        session.add(record)
        session.flush()
        return record

    @staticmethod
    def to_result(record: PathValidationModel) -> PathValidationResult:
        from app.domain.path_validation import PathValidationSnapshot
        return PathValidationResult(snapshot=PathValidationSnapshot.model_validate(record.snapshot))

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)