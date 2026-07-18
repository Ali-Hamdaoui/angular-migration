"""Persist run-scoped source snapshot records."""

from alembic import op
import sqlalchemy as sa

revision = "20260715_03"
down_revision = "20260715_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("snapshot_path", sa.Text(), nullable=False),
        sa.Column("manifest_id", sa.String(128)),
        sa.Column("fingerprint", sa.String(128)),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exclusions", sa.JSON(), nullable=False),
        sa.Column("git_metadata", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("event_sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_source_snapshots_run_idempotency"),
    )
    op.create_index("ix_source_snapshots_run_id", "source_snapshots", ["run_id"])
    op.create_index("ix_source_snapshots_status", "source_snapshots", ["status"])


def downgrade() -> None:
    op.drop_index("ix_source_snapshots_status", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_run_id", table_name="source_snapshots")
    op.drop_table("source_snapshots")
