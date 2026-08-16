"""Persist stage-chain runs (V2 F12-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_63"
down_revision = "20260817_62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_chain_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("source_major", sa.Integer(), nullable=False),
        sa.Column("target_major", sa.Integer(), nullable=False),
        sa.Column("catalogue_version", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stage_chain_runs_run_id", "stage_chain_runs", ["run_id"])
    op.create_index("ix_stage_chain_runs_checksum", "stage_chain_runs", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_stage_chain_runs_checksum", table_name="stage_chain_runs")
    op.drop_index("ix_stage_chain_runs_run_id", table_name="stage_chain_runs")
    op.drop_table("stage_chain_runs")
