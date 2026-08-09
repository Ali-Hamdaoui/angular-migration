"""Persist the authoritative G10 validation-target union on repair attempts."""

from alembic import op
import sqlalchemy as sa


revision = "20260803_43"
down_revision = "20260803_42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repair_attempts") as batch:
        batch.add_column(sa.Column("validation_targets", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table("repair_attempts") as batch:
        batch.drop_column("validation_targets")
