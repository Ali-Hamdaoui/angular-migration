"""Persist S2-F05 feasibility evidence and G05 decisions."""

from alembic import op
import sqlalchemy as sa

revision = "20260719_04"
down_revision = "20260719_03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "compatibility_catalogues",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("version", name="uq_compatibility_catalogues_version"),
    )
    op.create_table(
        "compatibility_registry_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "snapshot_id", name="uq_compatibility_registry_run_snapshot"),
    )
    op.create_index("ix_compatibility_registry_snapshots_run_id", "compatibility_registry_snapshots", ["run_id"])
    op.create_table(
        "compatibility_resolutions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("catalogue_version", sa.String(128), nullable=False),
        sa.Column("catalogue_checksum", sa.String(128), nullable=False),
        sa.Column("registry_snapshot_id", sa.String(128), nullable=False),
        sa.Column("registry_snapshot_checksum", sa.String(128), nullable=False),
        sa.Column("registry_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("runtime_candidates", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source_exact", sa.String(64), nullable=False),
        sa.Column("source_family", sa.String(64), nullable=False),
        sa.Column("target_family", sa.String(64), nullable=False),
        sa.Column("support_level", sa.String(48), nullable=False),
        sa.Column("route", sa.JSON(), nullable=False),
        sa.Column("selected_profile", sa.JSON()),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("package", sa.JSON(), nullable=False),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128)),
        sa.Column("plan_version", sa.String(128)),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_compatibility_resolutions_run_idempotency"),
    )
    op.create_index("ix_compatibility_resolutions_run_id", "compatibility_resolutions", ["run_id"])
    op.create_index("ix_compatibility_resolutions_status", "compatibility_resolutions", ["status"])
    op.create_table(
        "g05_approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(64)),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128)),
        sa.Column("plan_version", sa.String(128)),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("stale_reason", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g05_approvals_run_idempotency"),
    )
    op.create_index("ix_g05_approvals_run_id", "g05_approvals", ["run_id"])
    op.create_index("ix_g05_approvals_status", "g05_approvals", ["status"])


def downgrade():
    op.drop_index("ix_g05_approvals_status", table_name="g05_approvals")
    op.drop_index("ix_g05_approvals_run_id", table_name="g05_approvals")
    op.drop_table("g05_approvals")
    op.drop_index("ix_compatibility_resolutions_status", table_name="compatibility_resolutions")
    op.drop_index("ix_compatibility_resolutions_run_id", table_name="compatibility_resolutions")
    op.drop_table("compatibility_resolutions")
    op.drop_index("ix_compatibility_registry_snapshots_run_id", table_name="compatibility_registry_snapshots")
    op.drop_table("compatibility_registry_snapshots")
    op.drop_table("compatibility_catalogues")
