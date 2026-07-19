"""Add unique constraint on reconciliation_runs.idempotency_key.

Revision ID: 20260720_02_reconciliation_idempotency
Revises: 20260720_01_reconciliation_assistant
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_02_reconciliation_idempotency"
down_revision: str | None = "20260720_01_reconciliation_assistant"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # SQLite requires a single-statement approach: drop existing index,
    # then create unique index.
    # Drop the old non-unique index if it exists
    op.execute(
        "DROP INDEX IF EXISTS ix_reconciliation_runs_idempotency_key"
    )
    # Create unique index (SQLAlchemy-style name for UniqueConstraint)
    op.create_index(
        "uq_reconciliation_runs_idempotency",
        "reconciliation_runs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=None,
    )


def downgrade() -> None:
    op.drop_index("uq_reconciliation_runs_idempotency", table_name="reconciliation_runs")
    # Restore the non-unique index
    op.create_index(
        "ix_reconciliation_runs_idempotency_key",
        "reconciliation_runs",
        ["idempotency_key"],
        unique=False,
    )
