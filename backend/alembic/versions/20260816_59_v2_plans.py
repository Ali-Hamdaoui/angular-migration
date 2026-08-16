"""Persist V2 migration plans (F18-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_59"
down_revision = "20260816_58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_plans",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("source_major", sa.Integer(), nullable=False),
        sa.Column("target_major", sa.Integer(), nullable=False),
        sa.Column("catalogue_version", sa.String(length=128), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_v2_plans_run_id", "v2_plans", ["run_id"])
    op.create_index("ix_v2_plans_checksum", "v2_plans", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_v2_plans_checksum", table_name="v2_plans")
    op.drop_index("ix_v2_plans_run_id", table_name="v2_plans")
    op.drop_table("v2_plans")
