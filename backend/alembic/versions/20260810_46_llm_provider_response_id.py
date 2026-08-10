"""Persist provider response identifiers for safe response retrieval."""

from alembic import op
import sqlalchemy as sa


revision = "20260810_46"
down_revision = "20260802_45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_invocations") as batch:
        batch.add_column(sa.Column("provider_response_id", sa.String(length=256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("llm_invocations") as batch:
        batch.drop_column("provider_response_id")
