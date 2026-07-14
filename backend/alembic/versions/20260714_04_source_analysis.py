"""Persist deterministic source-analysis results."""

from alembic import op
import sqlalchemy as sa

revision = "20260714_04"
down_revision = "20260714_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_analyses",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_source_analysis_idempotency"),
    )
    op.create_index("ix_source_analyses_status", "source_analyses", ["status"])


def downgrade() -> None:
    op.drop_index("ix_source_analyses_status", table_name="source_analyses")
    op.drop_table("source_analyses")