"""Persistence model for catalogue certification evidence (V2 F30-04)."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class CatalogueCertificationModel(Base):
    """One entry's durable certification evidence + audit (F30-04)."""

    __tablename__ = "catalogue_certifications"
    __table_args__ = (
        UniqueConstraint("source_family", "target_family", "run_id", name="uq_catalogue_cert_source_target_run"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    runtime_proof: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    catalogue_version: Mapped[str] = mapped_column(String(128), nullable=False)
    deterministic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
