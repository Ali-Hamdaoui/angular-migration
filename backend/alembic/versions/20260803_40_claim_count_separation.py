"""Separate claim counting from env-transient retry accounting (T05).

Claim attempts (lease acquisition and expired-lease reclaim) no longer
consume the continuation's env-transient retry budget.  The new nullable
claim_count column counts every claim, while attempt stays reserved for
env-transient retries incremented at the classification layer.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_40"
down_revision = "20260803_39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transformation_continuations",
        sa.Column("claim_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transformation_continuations", "claim_count")
