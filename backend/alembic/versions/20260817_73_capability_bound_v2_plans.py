"""Bind V2 plans to immutable capability snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_73"
down_revision = "20260817_72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("v2_plans", sa.Column("capability_snapshot_id", sa.String(length=64), nullable=True))
    op.add_column("v2_plans", sa.Column("capability_snapshot_checksum", sa.String(length=128), nullable=True))
    op.create_index("ix_v2_plans_capability_snapshot_id", "v2_plans", ["capability_snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_v2_plans_capability_snapshot_id", table_name="v2_plans")
    op.drop_column("v2_plans", "capability_snapshot_checksum")
    op.drop_column("v2_plans", "capability_snapshot_id")
