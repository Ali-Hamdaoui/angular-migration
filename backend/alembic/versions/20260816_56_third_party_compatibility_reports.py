"""Persist third-party compatibility reports (V2 F15-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_56"
down_revision = "20260816_55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "third_party_compatibility_reports",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("source_major", sa.Integer(), nullable=False),
        sa.Column("target_major", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("inventory", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tpc_reports_run_id", "third_party_compatibility_reports", ["run_id"])
    op.create_index("ix_tpc_reports_stage_id", "third_party_compatibility_reports", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_tpc_reports_stage_id", table_name="third_party_compatibility_reports")
    op.drop_index("ix_tpc_reports_run_id", table_name="third_party_compatibility_reports")
    op.drop_table("third_party_compatibility_reports")
