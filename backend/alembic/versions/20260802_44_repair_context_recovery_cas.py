"""Add a CAS version to repair attempts for immutable context recovery."""

from alembic import op
import sqlalchemy as sa


revision = "20260802_44"
down_revision = "20260803_43"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repair_attempts") as batch:
        batch.add_column(sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("repair_attempts") as batch:
        batch.drop_column("state_version")
