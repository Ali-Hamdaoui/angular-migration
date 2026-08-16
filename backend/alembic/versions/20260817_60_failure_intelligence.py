"""Persist failure intelligence snapshots (V2 F19-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_60"
down_revision = "20260816_59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failure_intelligence",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("groups", sa.JSON(), nullable=False),
        sa.Column("root_causes", sa.JSON(), nullable=False),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_failure_intelligence_run_id", "failure_intelligence", ["run_id"])
    op.create_index("ix_failure_intelligence_checksum", "failure_intelligence", ["checksum"])
    op.create_index("uq_failure_intelligence_run_checksum", "failure_intelligence", ["run_id", "checksum"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_failure_intelligence_run_checksum", table_name="failure_intelligence")
    op.drop_index("ix_failure_intelligence_checksum", table_name="failure_intelligence")
    op.drop_index("ix_failure_intelligence_run_id", table_name="failure_intelligence")
    op.drop_table("failure_intelligence")
