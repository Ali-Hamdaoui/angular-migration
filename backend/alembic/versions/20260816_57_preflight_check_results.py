"""Persist preflight check results (V2 F16-02)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_57"
down_revision = "20260816_56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preflight_check_results",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_preflight_check_run_id", "preflight_check_results", ["run_id"])
    op.create_index("ix_preflight_check_checksum", "preflight_check_results", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_preflight_check_checksum", table_name="preflight_check_results")
    op.drop_index("ix_preflight_check_run_id", table_name="preflight_check_results")
    op.drop_table("preflight_check_results")
