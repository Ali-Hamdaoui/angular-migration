"""Add G07 approval gate and stage workspace tables for S3-F05/S3-F06."""

from alembic import op
import sqlalchemy as sa

revision = "20260720_01"
down_revision = "20260719_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # G07 approval gate table
    op.create_table(
        "g07_approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(64)),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("plan_version", sa.String(64), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("package", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("stale_reason", sa.Text()),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g07_approvals_run_idempotency"),
    )
    op.create_index("ix_g07_approvals_run_id", "g07_approvals", ["run_id"])
    op.create_index("ix_g07_approvals_stage_id", "g07_approvals", ["stage_id"])
    op.create_index("ix_g07_approvals_status", "g07_approvals", ["status"])

    # Stage workspace tracking table
    op.create_table(
        "stage_workspaces",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("sandbox_path", sa.Text(), nullable=False),
        sa.Column("source_fingerprint", sa.String(128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_size_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("copy_status", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("verification_checksum", sa.String(128)),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("event_sequence", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "stage_id", name="uq_stage_workspaces_run_stage"),
    )
    op.create_index("ix_stage_workspaces_run_id", "stage_workspaces", ["run_id"])
    op.create_index("ix_stage_workspaces_stage_id", "stage_workspaces", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_stage_workspaces_stage_id", table_name="stage_workspaces")
    op.drop_index("ix_stage_workspaces_run_id", table_name="stage_workspaces")
    op.drop_table("stage_workspaces")
    op.drop_index("ix_g07_approvals_status", table_name="g07_approvals")
    op.drop_index("ix_g07_approvals_stage_id", table_name="g07_approvals")
    op.drop_index("ix_g07_approvals_run_id", table_name="g07_approvals")
    op.drop_table("g07_approvals")
