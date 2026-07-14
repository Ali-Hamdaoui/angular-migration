"""Persistence access for environment capability snapshots and diagnostic events."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.system import EnvironmentCapabilityResult
from app.repositories.models import EnvironmentCapabilityModel, EnvironmentDiagnosticEventModel


class EnvironmentCapabilityRepository:
    def get_by_idempotency(self, session: Session, idempotency_key: str) -> EnvironmentCapabilityModel | None:
        return session.scalar(
            select(EnvironmentCapabilityModel).where(
                EnvironmentCapabilityModel.idempotency_key == idempotency_key
            )
        )

    def get_latest(self, session: Session) -> EnvironmentCapabilityModel | None:
        return session.scalar(
            select(EnvironmentCapabilityModel).order_by(EnvironmentCapabilityModel.created_at.desc()).limit(1)
        )

    def save(
        self,
        session: Session,
        result: EnvironmentCapabilityResult,
        *,
        idempotency_key: str,
        actor: str | None,
        now: datetime,
    ) -> EnvironmentCapabilityModel:
        record = EnvironmentCapabilityModel(
            id=result.snapshot.snapshot_id,
            idempotency_key=idempotency_key,
            actor=actor,
            status=result.snapshot.status,
            captured_at=result.snapshot.captured_at,
            policy_version=result.snapshot.policy_version,
            checksum=result.snapshot.checksum,
            snapshot=result.snapshot.model_dump(mode="json"),
            artifacts=result.artifact,
            created_at=now,
        )
        session.add(record)
        session.flush()
        session.add_all(
            [
                EnvironmentDiagnosticEventModel(
                    id=f"environment-event-{uuid4().hex}",
                    snapshot_id=result.snapshot.snapshot_id,
                    event_type="ENVIRONMENT_DIAGNOSTICS_STARTED",
                    idempotency_key=f"{idempotency_key}:started",
                    actor=actor,
                    payload={"snapshot_id": result.snapshot.snapshot_id},
                    occurred_at=now,
                ),
                EnvironmentDiagnosticEventModel(
                    id=f"environment-event-{uuid4().hex}",
                    snapshot_id=result.snapshot.snapshot_id,
                    event_type=(
                        "ENVIRONMENT_DIAGNOSTICS_BLOCKED"
                        if result.snapshot.status == "blocked"
                        else "ENVIRONMENT_DIAGNOSTICS_COMPLETED"
                    ),
                    idempotency_key=f"{idempotency_key}:completed",
                    actor=actor,
                    payload={
                        "snapshot_id": result.snapshot.snapshot_id,
                        "checksum": result.snapshot.checksum,
                        "status": result.snapshot.status,
                    },
                    occurred_at=now,
                ),
            ]
        )
        return record

    @staticmethod
    def to_result(record: EnvironmentCapabilityModel) -> EnvironmentCapabilityResult:
        from app.domain.system import EnvironmentCapabilitySnapshot

        return EnvironmentCapabilityResult(
            snapshot=EnvironmentCapabilitySnapshot.model_validate(record.snapshot),
            artifact=record.artifacts,
        )