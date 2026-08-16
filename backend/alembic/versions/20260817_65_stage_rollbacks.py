"""Persist stage rollbacks (V2 F25-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_65"
down_revision = "20260817_64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_rollbacks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("rollback_point_stage_order", sa.Integer(), nullable=True),
        sa.Column("sealed_stage_count", sa.Integer(), nullable=False),
        sa.Column("evidence_preserved", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stage_rollbacks_run_id", "stage_rollbacks", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_stage_rollbacks_run_id", table_name="stage_rollbacks")
    op.drop_table("stage_rollbacks")
