"""Persistence model for stage runtime bindings (V2 F02-05)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class StageRuntimeBindingModel(Base):
    __tablename__ = "stage_runtime_bindings"
    __table_args__ = (
        UniqueConstraint("stage_id", "kind", name="uq_stage_runtime_bindings_stage_kind"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    runtime_id: Mapped[str | None] = mapped_column(String(128))
    version_exact: Mapped[str | None] = mapped_column(String(64))
    sha256: Mapped[str | None] = mapped_column(String(64))
    resolved_path: Mapped[str | None] = mapped_column(String(1024))
    source: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
