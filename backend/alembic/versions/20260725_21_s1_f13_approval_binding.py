"""Persist S1-F13 request identity and G03 requalification state."""

from alembic import op
import sqlalchemy as sa


revision = "20260725_21"
down_revision = "20260724_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("baseline_parity_evidence", sa.Column("request_checksum", sa.String(128), nullable=True))
    op.add_column("baseline_assessments", sa.Column("stale_reason", sa.Text(), nullable=True))
    op.add_column("baseline_assessments", sa.Column("parity_binding", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("baseline_assessments", "stale_reason")
    op.drop_column("baseline_assessments", "parity_binding")
    op.drop_column("baseline_parity_evidence", "request_checksum")
