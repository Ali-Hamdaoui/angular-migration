"""Persist authoritative prepared-stage workspace bindings."""

from alembic import op
import sqlalchemy as sa


revision = "20260728_32"
down_revision = "20260727_31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_workspace_bindings",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_id", sa.String(length=64), nullable=False),
        sa.Column("alias", sa.String(length=128), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "stage_id", "alias", name="uq_stage_workspace_binding"),
    )
    op.create_index("ix_stage_workspace_bindings_run_id", "stage_workspace_bindings", ["run_id"])
    op.create_index("ix_stage_workspace_bindings_stage_id", "stage_workspace_bindings", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_stage_workspace_bindings_stage_id", table_name="stage_workspace_bindings")
    op.drop_index("ix_stage_workspace_bindings_run_id", table_name="stage_workspace_bindings")
    op.drop_table("stage_workspace_bindings")
