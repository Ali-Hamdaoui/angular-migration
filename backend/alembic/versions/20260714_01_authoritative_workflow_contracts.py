"""Add authoritative workflow dimensions without rewriting Sprint 0 history.

Revision ID: 20260714_01
Revises: 20260710_01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260714_01"
down_revision = "20260710_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "migration_runs",
        sa.Column("phase_status", sa.String(length=64), nullable=False, server_default="running"),
    )
    op.add_column(
        "migration_runs",
        sa.Column("approval_status", sa.String(length=64), nullable=False, server_default="not_required"),
    )
    op.add_column(
        "migration_runs",
        sa.Column("repair_status", sa.String(length=64), nullable=False, server_default="not_required"),
    )

    # Preserve the old state and event history. Only the new dimensions are
    # initialized; no historical event rows are deleted or rewritten.
    op.execute(
        sa.text(
            "UPDATE migration_runs "
            "SET phase_status = CASE "
            "WHEN status IN ('COMPLETED', 'CANCELLED', 'FAILED') THEN 'completed' "
            "WHEN status = 'WAITING' THEN 'waiting_approval' "
            "ELSE 'running' END, "
            "approval_status = CASE "
            "WHEN status = 'WAITING' THEN 'pending' "
            "ELSE 'not_required' END"
        )
    )


def downgrade() -> None:
    op.drop_column("migration_runs", "repair_status")
    op.drop_column("migration_runs", "approval_status")
    op.drop_column("migration_runs", "phase_status")