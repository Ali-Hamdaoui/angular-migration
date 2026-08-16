"""Persist governed runtime eligibility classification."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_70"
down_revision = "20260817_69"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_certifications", sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("runtime_certifications", sa.Column("classification", sa.String(length=32), nullable=False, server_default="UNSUPPORTED"))


def downgrade() -> None:
    op.drop_column("runtime_certifications", "classification")
    op.drop_column("runtime_certifications", "allowed")
