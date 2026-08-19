"""Persist deterministic transformation replan recovery state (V2.1 Section 10)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_72"
down_revision = "20260817_71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transformation_replan_recoveries",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_checksum", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("new_plan_id", sa.String(length=128), nullable=False),
        sa.Column("new_plan_checksum", sa.String(length=128), nullable=False),
        sa.Column("new_stage_plan_id", sa.String(length=128), nullable=False),
        sa.Column("new_stage_plan_checksum", sa.String(length=128), nullable=False),
        sa.Column("new_g06_id", sa.String(length=128), nullable=False),
        sa.Column("failure_group_key", sa.String(length=128), nullable=False),
        sa.Column("root_cause_code", sa.String(length=128), nullable=False),
        sa.Column("safe_checkpoint_id", sa.String(length=128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_transformation_replan_run_idempotency"),
    )
    op.create_index("ix_transformation_replan_run_id", "transformation_replan_recoveries", ["run_id"])
    op.create_index("ix_transformation_replan_stage_id", "transformation_replan_recoveries", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_transformation_replan_stage_id", table_name="transformation_replan_recoveries")
    op.drop_index("ix_transformation_replan_run_id", table_name="transformation_replan_recoveries")
    op.drop_table("transformation_replan_recoveries")
