"""Durable S2-F05 feasibility, catalogue, registry, and G05 records."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class CompatibilityCatalogueModel(Base):
    __tablename__ = "compatibility_catalogues"
    __table_args__ = (UniqueConstraint("version", name="uq_compatibility_catalogues_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128))
    change_reason: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RegistrySnapshotModel(Base):
    __tablename__ = "compatibility_registry_snapshots"
    __table_args__ = (UniqueConstraint("run_id", "snapshot_id", name="uq_compatibility_registry_run_snapshot"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompatibilityResolutionModel(Base):
    __tablename__ = "compatibility_resolutions"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_compatibility_resolutions_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    catalogue_version: Mapped[str] = mapped_column(String(128), nullable=False)
    catalogue_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    registry_snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    registry_snapshot_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    registry_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    runtime_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    source_exact: Mapped[str] = mapped_column(String(64), nullable=False)
    source_family: Mapped[str] = mapped_column(String(64), nullable=False)
    target_family: Mapped[str] = mapped_column(String(64), nullable=False)
    support_level: Mapped[str] = mapped_column(String(48), nullable=False)
    route: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    selected_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_execution_profile_checksum: Mapped[str | None] = mapped_column(String(128))
    stage1_profile_checksum: Mapped[str | None] = mapped_column(String(128))
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    package: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    plan_version: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class G05ApprovalModel(Base):
    __tablename__ = "g05_approvals"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_g05_approvals_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str | None] = mapped_column(String(128))
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(64))
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    plan_version: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    prerequisite_artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    prerequisite_artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    input_bundle_checksum: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
