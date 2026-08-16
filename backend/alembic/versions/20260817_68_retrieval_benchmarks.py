"""Persist versioned retrieval benchmark reports (V2 F28-03)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_68"
down_revision = "20260817_67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retrieval_benchmarks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fixture_set", sa.String(length=64), nullable=False),
        sa.Column("case_results", sa.JSON(), nullable=False),
        sa.Column("mean_precision", sa.Float(), nullable=False),
        sa.Column("mean_recall", sa.Float(), nullable=False),
        sa.Column("mean_f1", sa.Float(), nullable=False),
        sa.Column("p95_latency_ms", sa.Float(), nullable=False),
        sa.Column("mean_budget_utilization", sa.Float(), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fixture_set", "version", name="uq_retrieval_benchmark_set_version"),
    )
    op.create_index("ix_retrieval_benchmarks_fixture_set", "retrieval_benchmarks", ["fixture_set"])


def downgrade() -> None:
    op.drop_index("ix_retrieval_benchmarks_fixture_set", table_name="retrieval_benchmarks")
    op.drop_table("retrieval_benchmarks")
