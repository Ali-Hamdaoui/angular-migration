"""Persist runtime execution evidence rows (V2 F01-04)."""

import sqlalchemy as sa

from alembic import op

revision = "20260815_47"
down_revision = "20260810_46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_execution_evidence",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("execution_id", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("executable_name", sa.String(length=128), nullable=False),
        sa.Column("resolved_path", sa.String(length=1024), nullable=False),
        sa.Column("version_exact", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("operating_system", sa.String(length=32), nullable=False),
        sa.Column("architecture", sa.String(length=32), nullable=False),
        sa.Column("installation_root", sa.String(length=1024), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("runtime_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_runtime_evidence_run_idempotency"),
    )
    op.create_index("ix_runtime_evidence_run_id", "runtime_execution_evidence", ["run_id"])
    op.create_index("ix_runtime_evidence_execution_id", "runtime_execution_evidence", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_runtime_evidence_execution_id", table_name="runtime_execution_evidence")
    op.drop_index("ix_runtime_evidence_run_id", table_name="runtime_execution_evidence")
    op.drop_table("runtime_execution_evidence")
