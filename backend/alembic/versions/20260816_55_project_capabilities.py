"""Persist project capability snapshots (V2 F13-03)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_55"
down_revision = "20260816_54"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_capabilities",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=True),
        sa.Column("source_root", sa.String(length=1024), nullable=False),
        sa.Column("angular_major", sa.Integer(), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_capabilities_run_id", "project_capabilities", ["run_id"])
    op.create_index("ix_project_capabilities_stage_id", "project_capabilities", ["stage_id"])
    op.create_index("ix_project_capabilities_checksum", "project_capabilities", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_project_capabilities_checksum", table_name="project_capabilities")
    op.drop_index("ix_project_capabilities_stage_id", table_name="project_capabilities")
    op.drop_index("ix_project_capabilities_run_id", table_name="project_capabilities")
    op.drop_table("project_capabilities")
