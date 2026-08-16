"""Persist workspace generations (V2 F07)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_50"
down_revision = "20260816_49"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_generations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=True),
        sa.Column("alias", sa.String(length=128), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_binding_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "stage_id", "alias", "generation", name="uq_workspace_generation"),
    )
    op.create_index("ix_workspace_generations_run_id", "workspace_generations", ["run_id"])
    op.create_index("ix_workspace_generations_stage_id", "workspace_generations", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_workspace_generations_stage_id", table_name="workspace_generations")
    op.drop_index("ix_workspace_generations_run_id", table_name="workspace_generations")
    op.drop_table("workspace_generations")
