"""Persist failure diagnostic packs (V2 F03-02)."""

import sqlalchemy as sa

from alembic import op

revision = "20260815_48"
down_revision = "20260815_47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failure_diagnostic_packs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=True),
        sa.Column("execution_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("fault_code", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("workflow_context", sa.JSON(), nullable=False),
        sa.Column("command_evidence", sa.JSON(), nullable=True),
        sa.Column("sanitized_traceback", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_diag_pack_run_id", "failure_diagnostic_packs", ["run_id"])
    op.create_index("ix_diag_pack_execution_id", "failure_diagnostic_packs", ["execution_id"])
    op.create_index("ix_diag_pack_fault_code", "failure_diagnostic_packs", ["fault_code"])


def downgrade() -> None:
    op.drop_index("ix_diag_pack_fault_code", table_name="failure_diagnostic_packs")
    op.drop_index("ix_diag_pack_execution_id", table_name="failure_diagnostic_packs")
    op.drop_index("ix_diag_pack_run_id", table_name="failure_diagnostic_packs")
    op.drop_table("failure_diagnostic_packs")
