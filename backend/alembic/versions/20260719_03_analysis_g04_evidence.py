"""Persist Analysis evidence and the checksum-bound G04 gate."""

from alembic import op
import sqlalchemy as sa

revision = "20260719_03"
down_revision = "20260719_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analysis_metadata",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("prerequisite_artifact_ids", sa.JSON(), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128)),
        sa.Column("plan_version", sa.String(128)),
        sa.Column("invocation_id", sa.String(64), sa.ForeignKey("llm_invocations.id")),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False),
        sa.Column("package", sa.JSON()),
        sa.Column("error_code", sa.String(128)),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_analysis_metadata_run_idempotency"),
    )
    op.create_index("ix_analysis_metadata_run_id", "analysis_metadata", ["run_id"])
    op.create_index("ix_analysis_metadata_invocation_id", "analysis_metadata", ["invocation_id"])
    op.create_index("ix_analysis_metadata_status", "analysis_metadata", ["status"])
    op.create_table(
        "g04_approvals",
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g04_approvals_run_idempotency"),
    )
    op.create_index("ix_g04_approvals_run_id", "g04_approvals", ["run_id"])
    op.create_index("ix_g04_approvals_status", "g04_approvals", ["status"])


def downgrade():
    op.drop_index("ix_g04_approvals_status", table_name="g04_approvals")
    op.drop_index("ix_g04_approvals_run_id", table_name="g04_approvals")
    op.drop_table("g04_approvals")
    op.drop_index("ix_analysis_metadata_status", table_name="analysis_metadata")
    op.drop_index("ix_analysis_metadata_invocation_id", table_name="analysis_metadata")
    op.drop_index("ix_analysis_metadata_run_id", table_name="analysis_metadata")
    op.drop_table("analysis_metadata")
