"""Create failures and failure_diagnostics tables for failure evidence persistence.

Revision ID: 20260719_07_g05
Revises: 20260719_06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260719_07_g05"
down_revision = "20260719_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failures",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), index=True),
        sa.Column("execution_id", sa.String(128), index=True),
        sa.Column("failure_fingerprint", sa.String(128), nullable=False, index=True),
        sa.Column("origin", sa.String(64), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("failure_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_failures_run_idempotency"),
    )
    op.create_index("ix_failures_run_id", "failures", ["run_id"])
    op.create_index("ix_failures_fingerprint", "failures", ["failure_fingerprint"])
    op.create_index("ix_failures_status", "failures", ["status"])

    op.create_table(
        "failure_diagnostics",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("failure_id", sa.String(64), sa.ForeignKey("failures.id"), nullable=False, index=True),
        sa.Column("parser_type", sa.String(64), nullable=False),
        sa.Column("parser_confidence", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("code", sa.String(128)),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("line_number", sa.Integer()),
        sa.Column("column", sa.Integer()),
        sa.Column("severity", sa.String(32)),
        sa.Column("raw_excerpt", sa.Text()),
    )
    op.create_index("ix_failure_diagnostics_failure_id", "failure_diagnostics", ["failure_id"])


def downgrade() -> None:
    op.drop_index("ix_failure_diagnostics_failure_id", table_name="failure_diagnostics")
    op.drop_table("failure_diagnostics")
    op.drop_index("ix_failures_status", table_name="failures")
    op.drop_index("ix_failures_fingerprint", table_name="failures")
    op.drop_index("ix_failures_run_id", table_name="failures")
    op.drop_table("failures")
