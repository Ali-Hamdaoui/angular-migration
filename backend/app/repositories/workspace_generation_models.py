"""Persistence model for workspace generations (V2 F07)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class WorkspaceGenerationModel(Base):
    __tablename__ = "workspace_generations"
    __table_args__ = (
        UniqueConstraint("run_id", "stage_id", "alias", "generation", name="uq_workspace_generation"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    input_fingerprint: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    active_binding_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
