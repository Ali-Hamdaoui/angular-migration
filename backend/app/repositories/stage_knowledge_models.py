"""Persistence model for stage knowledge entries (V2 F17-03)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class StageKnowledgeEntryModel(Base):
    __tablename__ = "stage_knowledge_entries"
    __table_args__ = (
        UniqueConstraint("source_major", "target_major", "version", name="uq_stage_knowledge_transition_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_major: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    target_major: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    expected_transforms: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    validation_expectations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expected_dependency_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    dependency_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    migration_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    known_risks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128))
    change_reason: Mapped[str | None] = mapped_column(String(512))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
