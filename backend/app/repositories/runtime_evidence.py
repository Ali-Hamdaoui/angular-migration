"""Persistence model for runtime execution evidence (V2 F01-04).

Every resolved runtime executable fact (path, version, checksum) is durable
state that proves which runtime a migration policy bound for execution.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class RuntimeExecutionEvidenceModel(Base):
    __tablename__ = "runtime_execution_evidence"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_runtime_evidence_run_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    execution_id: Mapped[str | None] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    executable_name: Mapped[str] = mapped_column(String(128), nullable=False)
    resolved_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    version_exact: Mapped[str | None] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    operating_system: Mapped[str] = mapped_column(String(32), nullable=False)
    architecture: Mapped[str] = mapped_column(String(32), nullable=False)
    installation_root: Mapped[str | None] = mapped_column(String(1024))
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
