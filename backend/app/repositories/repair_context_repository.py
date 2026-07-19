"""Repository for RepairContextPack persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.repair_context import RepairContextPack
from app.repositories.models.workflow import RepairContextPackModel


class RepairContextRepository:
    """Repository for RepairContextPackModel persistence."""

    def save_context_pack(
        self,
        session: Session,
        pack: RepairContextPack,
        idempotency_key: str,
        state_version: int,
    ) -> RepairContextPackModel:
        """Persist a new or updated repair context pack and return the ORM model.

        Uses idempotency key to avoid duplicate inserts — if a record with the
        same run_id and idempotency_key already exists the existing record is
        returned unchanged.
        """
        existing = (
            session.query(RepairContextPackModel)
            .filter(
                RepairContextPackModel.run_id == pack.failure_id,
                RepairContextPackModel.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing is not None:
            return existing

        now = datetime.now(UTC)
        model = RepairContextPackModel(
            id=pack.context_pack_id,
            run_id=pack.failure_id,
            failure_id=pack.failure_id,
            stage_id=pack.stage_id,
            repair_attempt=pack.repair_attempt,
            workspace_fingerprint=pack.workspace_fingerprint,
            selection_policy_version=pack.selection_policy_version,
            sanitization_checksum=pack.sanitization_checksum,
            content_checksum=pack.content_checksum,
            token_budget=pack.token_budget,
            status=pack.status.value if hasattr(pack.status, "value") else pack.status,
            context_json=pack.model_dump_json(indent=2),
            idempotency_key=idempotency_key,
            state_version=state_version,
            created_at=now,
        )
        session.add(model)
        session.flush()
        return model

    def get_context_pack(
        self,
        session: Session,
        run_id: str,
        context_pack_id: str,
    ) -> RepairContextPackModel | None:
        """Retrieve a context pack by its ID, scoped to run."""
        return session.query(RepairContextPackModel).filter(
            RepairContextPackModel.id == context_pack_id,
            RepairContextPackModel.run_id == run_id,
        ).first()

    def get_context_packs_by_failure(
        self,
        session: Session,
        failure_id: str,
    ) -> list[RepairContextPackModel]:
        """Retrieve all context packs for a failure, ordered by creation time."""
        return session.query(RepairContextPackModel).filter(
            RepairContextPackModel.failure_id == failure_id,
        ).order_by(RepairContextPackModel.created_at.desc()).all()
