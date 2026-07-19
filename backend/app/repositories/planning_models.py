"""Durable MigrationPlan and StageExecutionPlan evidence records for S2-F06-I02."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class MigrationPlanModel(Base):
    __tablename__ = "migration_plans"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_migration_plans_run_idempotency"),
        UniqueConstraint("run_id", "version", name="uq_migration_plans_run_version"),
        Index("ix_migration_plans_run_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageExecutionPlanModel(Base):
    __tablename__ = "stage_execution_plans"
    __table_args__ = (
        UniqueConstraint("run_id", "stage_id", "version", name="uq_stage_execution_plans_run_stage_version"),
        UniqueConstraint("run_id", "stage_id", "idempotency_key", name="uq_stage_execution_plans_run_stage_idempotency"),
        Index("ix_stage_execution_plans_run_id", "run_id"),
        Index("ix_stage_execution_plans_stage_id", "stage_id"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False)
    migration_plan_id: Mapped[str] = mapped_column(ForeignKey("migration_plans.id"), nullable=False)
    stage_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BuildSystemDecisionModel(Base):
    __tablename__ = "build_system_decisions"
    __table_args__ = (UniqueConstraint("run_id", "decision_id", name="uq_build_system_decisions_run_decision"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_plan_id: Mapped[str] = mapped_column(ForeignKey("stage_execution_plans.id"), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActivePlanVersionModel(Base):
    __tablename__ = "active_plan_versions"
    __table_args__ = (UniqueConstraint("run_id", "scope", name="uq_active_plan_versions_run_scope"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    migration_plan_id: Mapped[str] = mapped_column(ForeignKey("migration_plans.id"), nullable=False)
    stage_plan_id: Mapped[str | None] = mapped_column(ForeignKey("stage_execution_plans.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
