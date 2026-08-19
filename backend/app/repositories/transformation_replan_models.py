"""Durable transformation replan/recovery records (V2.1 Section 10)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class TransformationReplanRecoveryModel(Base):
    __tablename__ = "transformation_replan_recoveries"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_transformation_replan_run_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    new_plan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    new_plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    new_stage_plan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    new_stage_plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    new_g06_id: Mapped[str] = mapped_column(String(128), nullable=False)
    failure_group_key: Mapped[str] = mapped_column(String(128), nullable=False)
    root_cause_code: Mapped[str] = mapped_column(String(128), nullable=False)
    safe_checkpoint_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
