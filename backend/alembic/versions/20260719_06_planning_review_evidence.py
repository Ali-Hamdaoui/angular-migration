"""Persist S2-F07 plan review, revision, and G06 evidence."""

from alembic import op
import sqlalchemy as sa


revision = "20260719_06"
down_revision = "20260719_05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plan_revisions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("previous_plan_id", sa.String(128), sa.ForeignKey("migration_plans.id"), nullable=False),
        sa.Column("migration_plan_id", sa.String(128), sa.ForeignKey("migration_plans.id"), nullable=False),
        sa.Column("stage_plan_id", sa.String(128), sa.ForeignKey("stage_execution_plans.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("diff_checksum", sa.String(128), nullable=False),
        sa.Column("stale_approval_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_plan_revisions_run_idempotency"),
        sa.UniqueConstraint("run_id", "version", name="uq_plan_revisions_run_version"),
    )
    op.create_index("ix_plan_revisions_run_id", "plan_revisions", ["run_id"])
    op.create_index("ix_plan_revisions_status", "plan_revisions", ["status"])

    op.create_table(
        "planning_reviews",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("migration_plan_id", sa.String(128), sa.ForeignKey("migration_plans.id"), nullable=False),
        sa.Column("stage_plan_id", sa.String(128), sa.ForeignKey("stage_execution_plans.id"), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("package", sa.JSON()),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False),
        sa.Column("proposer_invocation_id", sa.String(64), sa.ForeignKey("llm_invocations.id")),
        sa.Column("reviewer_invocation_id", sa.String(64), sa.ForeignKey("llm_invocations.id")),
        sa.Column("error_code", sa.String(128)),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_planning_reviews_run_idempotency"),
    )
    op.create_index("ix_planning_reviews_run_id", "planning_reviews", ["run_id"])
    op.create_index("ix_planning_reviews_status", "planning_reviews", ["status"])

    op.create_table(
        "plan_approval_stale_records",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(32), nullable=False),
        sa.Column("approval_id", sa.String(128), nullable=False),
        sa.Column("previous_plan_version", sa.Integer(), nullable=False),
        sa.Column("new_plan_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_plan_approval_stale_run_id", "plan_approval_stale_records", ["run_id"])

    op.create_table(
        "g06_approvals",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(64)),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("plan_checksum", sa.String(128), nullable=False),
        sa.Column("stage_plan_checksum", sa.String(128), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128)),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("stale_reason", sa.Text()),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g06_approvals_run_idempotency"),
    )
    op.create_index("ix_g06_approvals_run_id", "g06_approvals", ["run_id"])
    op.create_index("ix_g06_approvals_status", "g06_approvals", ["status"])


def downgrade():
    op.drop_index("ix_g06_approvals_status", table_name="g06_approvals")
    op.drop_index("ix_g06_approvals_run_id", table_name="g06_approvals")
    op.drop_table("g06_approvals")
    op.drop_index("ix_plan_approval_stale_run_id", table_name="plan_approval_stale_records")
    op.drop_table("plan_approval_stale_records")
    op.drop_index("ix_planning_reviews_status", table_name="planning_reviews")
    op.drop_index("ix_planning_reviews_run_id", table_name="planning_reviews")
    op.drop_table("planning_reviews")
    op.drop_index("ix_plan_revisions_status", table_name="plan_revisions")
    op.drop_index("ix_plan_revisions_run_id", table_name="plan_revisions")
    op.drop_table("plan_revisions")
