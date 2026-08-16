"""Persist stage runtime bindings (V2 F02-05)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_49"
down_revision = "20260815_48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_runtime_bindings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("runtime_id", sa.String(length=128), nullable=True),
        sa.Column("version_exact", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("resolved_path", sa.String(length=1024), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blocked_reason", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stage_id", "kind", name="uq_stage_runtime_bindings_stage_kind"),
    )
    op.create_index("ix_stage_runtime_bindings_run_id", "stage_runtime_bindings", ["run_id"])
    op.create_index("ix_stage_runtime_bindings_stage_id", "stage_runtime_bindings", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_stage_runtime_bindings_stage_id", table_name="stage_runtime_bindings")
    op.drop_index("ix_stage_runtime_bindings_run_id", table_name="stage_runtime_bindings")
    op.drop_table("stage_runtime_bindings")
