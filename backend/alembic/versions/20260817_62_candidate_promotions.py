"""Persist candidate promotions (V2 F22-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_62"
down_revision = "20260817_61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_promotions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("alias", sa.String(length=128), nullable=False),
        sa.Column("candidate_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("previous_generation", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_candidate_promotions_run_id", "candidate_promotions", ["run_id"])
    op.create_index("ix_candidate_promotions_stage_id", "candidate_promotions", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_candidate_promotions_stage_id", table_name="candidate_promotions")
    op.drop_index("ix_candidate_promotions_run_id", table_name="candidate_promotions")
    op.drop_table("candidate_promotions")
