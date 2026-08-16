"""Persist stage validation seals (V2 F24-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_64"
down_revision = "20260817_63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_validation_seals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("source_major", sa.Integer(), nullable=False),
        sa.Column("target_major", sa.Integer(), nullable=False),
        sa.Column("validation_checksum", sa.String(length=128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stage_validation_seals_stage_id", "stage_validation_seals", ["stage_id"], unique=True)
    op.create_index("ix_stage_validation_seals_run_id", "stage_validation_seals", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_stage_validation_seals_run_id", table_name="stage_validation_seals")
    op.drop_index("ix_stage_validation_seals_stage_id", table_name="stage_validation_seals")
    op.drop_table("stage_validation_seals")
