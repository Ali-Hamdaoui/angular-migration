"""Persistence model for the immutable execution audit trail (V2 F27-03)."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class CommandExecutionAuditModel(Base):
    """One immutable, append-only execution audit entry.

    Entries are never updated or deleted; a service wrapper is the only writer
    and enforces a hash chain over the entries.  The unique constraint binds an
    event to one run+execution+occurred timestamp so the chain is total.
    """

    __tablename__ = "command_execution_audits"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "execution_id",
            "occurred_at",
            "event",
            name="uq_cmd_exec_audit_run_exec_time_event",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    execution_id: Mapped[str | None] = mapped_column(String(64), index=True)
    command_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    command_class: Mapped[str] = mapped_column(String(64), nullable=False)
    event: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    actor: Mapped[str | None] = mapped_column(String(128))
    executable: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    arguments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    state_version: Mapped[int | None] = mapped_column(Integer)
    network_profile: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prev_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
