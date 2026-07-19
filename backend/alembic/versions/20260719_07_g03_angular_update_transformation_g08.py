"""Create G03 tables: angular_update_records, transformation_evidence, g08_approvals."""

from alembic import op
import sqlalchemy as sa


revision = "20260719_07"
down_revision = "20260719_06"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "angular_update_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("target_version_status", sa.String(32), nullable=False),
        sa.Column("resolved_target_version", sa.String(64)),
        sa.Column("source_version", sa.String(64), nullable=False),
        sa.Column("target_version", sa.String(64), nullable=False),
        sa.Column("command_execution_id", sa.String(64)),
        sa.Column("prompt_detected", sa.String(32), nullable=False, server_default="no_prompt"),
        sa.Column("evidence", sa.JSON()),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_angular_update_run_idempotency"),
    )
    op.create_index("ix_angular_update_records_run_id", "angular_update_records", ["run_id"])
    op.create_index("ix_angular_update_records_stage_id", "angular_update_records", ["stage_id"])
    op.create_index("ix_angular_update_records_status", "angular_update_records", ["status"])

    op.create_table(
        "transformation_evidence",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("overall_risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("total_files_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diff_checksum", sa.String(128), nullable=False),
        sa.Column("diff_summary", sa.JSON(), nullable=False),
        sa.Column("package_change_summary", sa.JSON()),
        sa.Column("migration_list", sa.JSON(), nullable=False, default=list),
        sa.Column("forbidden_changes", sa.JSON(), nullable=False, default=list),
        sa.Column("changed_file_classifications", sa.JSON(), nullable=False, default=dict),
        sa.Column("evidence_complete", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("block_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_transformation_evidence_run_idempotency"),
    )
    op.create_index("ix_transformation_evidence_run_id", "transformation_evidence", ["run_id"])
    op.create_index("ix_transformation_evidence_stage_id", "transformation_evidence", ["stage_id"])
    op.create_index("ix_transformation_evidence_status", "transformation_evidence", ["status"])

    op.create_table(
        "g08_approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(64)),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("package", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("stale_reason", sa.Text()),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g08_approvals_run_idempotency"),
    )
    op.create_index("ix_g08_approvals_run_id", "g08_approvals", ["run_id"])
    op.create_index("ix_g08_approvals_status", "g08_approvals", ["status"])


def downgrade():
    op.drop_index("ix_g08_approvals_status", table_name="g08_approvals")
    op.drop_index("ix_g08_approvals_run_id", table_name="g08_approvals")
    op.drop_table("g08_approvals")
    op.drop_index("ix_transformation_evidence_status", table_name="transformation_evidence")
    op.drop_index("ix_transformation_evidence_stage_id", table_name="transformation_evidence")
    op.drop_index("ix_transformation_evidence_run_id", table_name="transformation_evidence")
    op.drop_table("transformation_evidence")
    op.drop_index("ix_angular_update_records_status", table_name="angular_update_records")
    op.drop_index("ix_angular_update_records_stage_id", table_name="angular_update_records")
    op.drop_index("ix_angular_update_records_run_id", table_name="angular_update_records")
    op.drop_table("angular_update_records")
