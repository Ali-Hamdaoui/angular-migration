"""Add catalogue audit columns and record version snapshots (V2 F09-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_52"
down_revision = "20260816_51"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("compatibility_catalogues") as batch:
        batch.add_column(sa.Column("created_by", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("change_reason", sa.String(length=512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("compatibility_catalogues") as batch:
        batch.drop_column("change_reason")
        batch.drop_column("created_by")
