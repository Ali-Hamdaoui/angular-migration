"""Persistence model for source runtime resolution and selection."""
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.repositories.models.base import Base

class ExecutionProfileModel(Base):
    __tablename__ = "execution_profiles"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_execution_profiles_run_idempotency"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_angular_exact: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_profile_id: Mapped[str | None] = mapped_column(String(128))
    selected_checksum: Mapped[str | None] = mapped_column(String(128))
    profiles: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    guidance: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
