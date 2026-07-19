"""Persist S2-F06 plan evidence and active version pointers."""

from alembic import op
import sqlalchemy as sa


revision = "20260719_05"
down_revision = "20260719_04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "migration_plans",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_migration_plans_run_idempotency"),
        sa.UniqueConstraint("run_id", "version", name="uq_migration_plans_run_version"),
    )
    op.create_index("ix_migration_plans_run_id", "migration_plans", ["run_id"])
    op.create_index("ix_migration_plans_status", "migration_plans", ["status"])
    op.create_table(
        "stage_execution_plans",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("migration_plan_id", sa.String(128), sa.ForeignKey("migration_plans.id"), nullable=False),
        sa.Column("stage_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("stage_plan", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "stage_id", "version", name="uq_stage_execution_plans_run_stage_version"),
        sa.UniqueConstraint("run_id", "stage_id", "idempotency_key", name="uq_stage_execution_plans_run_stage_idempotency"),
    )
    op.create_index("ix_stage_execution_plans_run_id", "stage_execution_plans", ["run_id"])
    op.create_index("ix_stage_execution_plans_stage_id", "stage_execution_plans", ["stage_id"])
    op.create_index("ix_stage_execution_plans_status", "stage_execution_plans", ["status"])
    op.create_table(
        "build_system_decisions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_plan_id", sa.String(128), sa.ForeignKey("stage_execution_plans.id"), nullable=False),
        sa.Column("decision_id", sa.String(128), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "decision_id", name="uq_build_system_decisions_run_decision"),
    )
    op.create_index("ix_build_system_decisions_run_id", "build_system_decisions", ["run_id"])
    op.create_table(
        "active_plan_versions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("migration_plan_id", sa.String(128), sa.ForeignKey("migration_plans.id"), nullable=False),
        sa.Column("stage_plan_id", sa.String(128), sa.ForeignKey("stage_execution_plans.id")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "scope", name="uq_active_plan_versions_run_scope"),
    )
    op.create_index("ix_active_plan_versions_run_id", "active_plan_versions", ["run_id"])


def downgrade():
    op.drop_index("ix_active_plan_versions_run_id", table_name="active_plan_versions")
    op.drop_table("active_plan_versions")
    op.drop_index("ix_build_system_decisions_run_id", table_name="build_system_decisions")
    op.drop_table("build_system_decisions")
    op.drop_index("ix_stage_execution_plans_status", table_name="stage_execution_plans")
    op.drop_index("ix_stage_execution_plans_stage_id", table_name="stage_execution_plans")
    op.drop_index("ix_stage_execution_plans_run_id", table_name="stage_execution_plans")
    op.drop_table("stage_execution_plans")
    op.drop_index("ix_migration_plans_status", table_name="migration_plans")
    op.drop_index("ix_migration_plans_run_id", table_name="migration_plans")
    op.drop_table("migration_plans")
