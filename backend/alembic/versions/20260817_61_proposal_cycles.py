"""Persist governed proposal cycles (V2 F21-05)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_61"
down_revision = "20260817_60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_cycles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("attempt_id", sa.String(length=64), sa.ForeignKey("repair_attempts.id"), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("proposal_checksum", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("hints", sa.JSON(), nullable=False),
        sa.Column("parent_cycle_id", sa.String(length=64), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_proposal_cycles_run_id", "proposal_cycles", ["run_id"])
    op.create_index("ix_proposal_cycles_attempt_id", "proposal_cycles", ["attempt_id"])
    op.create_index("ix_proposal_cycles_parent", "proposal_cycles", ["parent_cycle_id"])


def downgrade() -> None:
    op.drop_index("ix_proposal_cycles_parent", table_name="proposal_cycles")
    op.drop_index("ix_proposal_cycles_attempt_id", table_name="proposal_cycles")
    op.drop_index("ix_proposal_cycles_run_id", table_name="proposal_cycles")
    op.drop_table("proposal_cycles")
