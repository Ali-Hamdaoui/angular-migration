"""Persist partial deliveries (V2 F26-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_66"
down_revision = "20260817_65"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partial_deliveries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("delivered_at_stage", sa.Integer(), nullable=True),
        sa.Column("delivered_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("remaining_stages", sa.JSON(), nullable=False),
        sa.Column("resumable", sa.Boolean(), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "checksum", name="uq_partial_deliveries_run_checksum"),
    )
    op.create_index("ix_partial_deliveries_run_id", "partial_deliveries", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_partial_deliveries_run_id", table_name="partial_deliveries")
    op.drop_table("partial_deliveries")
