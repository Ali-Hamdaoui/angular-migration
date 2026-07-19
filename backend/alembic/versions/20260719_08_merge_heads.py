"""Merge parallel heads from G05 failure evidence and routing branches.

Revision ID: 20260719_08
Revises: 20260719_07, 20260719_07_g05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260719_08"
down_revision = ("20260719_07", "20260719_07_g05")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
