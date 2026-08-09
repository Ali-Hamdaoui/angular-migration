"""Durable S2-F07 plan revision, Planning review, and G06 records."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class PlanRevisionModel(Base):
    __tablename__ = "plan_revisions"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_plan_revisions_run_idempotency"),
        UniqueConstraint("run_id", "version", name="uq_plan_revisions_run_version"),
        Index("ix_plan_revisions_run_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    previous_plan_id: Mapped[str] = mapped_column(ForeignKey("migration_plans.id"), nullable=False)
    migration_plan_id: Mapped[str] = mapped_column(ForeignKey("migration_plans.id"), nullable=False)
    stage_plan_id: Mapped[str] = mapped_column(ForeignKey("stage_execution_plans.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    diff: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    diff_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    stale_approval_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanningReviewModel(Base):
    __tablename__ = "planning_reviews"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_planning_reviews_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    migration_plan_id: Mapped[str] = mapped_column(ForeignKey("migration_plans.id"), nullable=False)
    stage_plan_id: Mapped[str] = mapped_column(ForeignKey("stage_execution_plans.id"), nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    package: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    proposer_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reviewer_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    revision_count: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(64), index=True)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    proposer_invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"))
    reviewer_invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"))
    error_code: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanApprovalStaleModel(Base):
    __tablename__ = "plan_approval_stale_records"
    __table_args__ = (Index("ix_plan_approval_stale_run_id", "run_id"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False)
    gate_id: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_id: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    new_plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class G06ApprovalModel(Base):
    __tablename__ = "g06_approvals"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_g06_approvals_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(64))
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    stage_plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class G06DecisionModel(Base):
    __tablename__ = "g06_decisions"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_g06_decisions_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    stage_plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
