"""Persistence model for bridge runtime certifications (V2 F11-02/04)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class RuntimeCertificationModel(Base):
    __tablename__ = "runtime_certifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    source_family: Mapped[str] = mapped_column(String(32), nullable=False)
    target_family: Mapped[str] = mapped_column(String(32), nullable=False)
    runtime_id: Mapped[str | None] = mapped_column(String(128))
    node_version: Mapped[str | None] = mapped_column(String(64))
    npm_version: Mapped[str | None] = mapped_column(String(64))
    node_sha256: Mapped[str | None] = mapped_column(String(64))
    npm_sha256: Mapped[str | None] = mapped_column(String(64))
    certified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512))
    certified_against: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
