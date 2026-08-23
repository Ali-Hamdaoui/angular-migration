"""Persist qualification-bypass evidence on compatibility resolutions."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_78"
down_revision = "20260819_77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("compatibility_resolutions") as batch:
        batch.add_column(sa.Column("qualification_evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("compatibility_resolutions") as batch:
        batch.drop_column("qualification_evidence")