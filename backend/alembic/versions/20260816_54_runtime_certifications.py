"""Persist bridge runtime certifications (V2 F11-02/04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_54"
down_revision = "20260816_53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_certifications",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("source_family", sa.String(length=32), nullable=False),
        sa.Column("target_family", sa.String(length=32), nullable=False),
        sa.Column("runtime_id", sa.String(length=128), nullable=True),
        sa.Column("node_version", sa.String(length=64), nullable=True),
        sa.Column("npm_version", sa.String(length=64), nullable=True),
        sa.Column("node_sha256", sa.String(length=64), nullable=True),
        sa.Column("npm_sha256", sa.String(length=64), nullable=True),
        sa.Column("certified", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("certified_against", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_runtime_certifications_run_id", "runtime_certifications", ["run_id"])
    op.create_index("ix_runtime_certifications_stage_id", "runtime_certifications", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_runtime_certifications_stage_id", table_name="runtime_certifications")
    op.drop_index("ix_runtime_certifications_run_id", table_name="runtime_certifications")
    op.drop_table("runtime_certifications")
