"""SQLAlchemy records owned by the production preflight boundary."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class PreflightModel(Base):
    __tablename__ = "preflights"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_preflights_idempotency"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    gate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    input_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    binding: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalGateModel(Base):
    __tablename__ = "approval_gates"
    __table_args__ = (UniqueConstraint("preflight_id", "gate_id", name="uq_approval_gates_preflight_gate"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preflight_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserDecisionModel(Base):
    __tablename__ = "user_decisions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_user_decisions_idempotency"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preflight_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    input_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PreflightEventModel(Base):
    __tablename__ = "preflight_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preflight_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
class PreflightArtifactMetadataModel(Base):
    __tablename__ = "preflight_artifact_metadata"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preflight_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
