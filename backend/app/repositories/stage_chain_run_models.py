"""Persistence model for stage-chain runs (V2 F12-04)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class StageChainRunModel(Base):
    __tablename__ = "stage_chain_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    source_major: Mapped[int] = mapped_column(Integer, nullable=False)
    target_major: Mapped[int] = mapped_column(Integer, nullable=False)
    catalogue_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
