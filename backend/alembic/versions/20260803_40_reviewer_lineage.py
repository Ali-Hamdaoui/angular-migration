"""Preserve the reviewer request-changes lineage on child repair attempts."""

from alembic import op
import sqlalchemy as sa


revision = "20260803_40"
down_revision = "20260803_39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repair_attempts") as batch:
        batch.add_column(sa.Column("parent_review_artifact_id", sa.String(128)))
        batch.add_column(sa.Column("parent_review_checksum", sa.String(128)))


def downgrade() -> None:
    with op.batch_alter_table("repair_attempts") as batch:
        batch.drop_column("parent_review_checksum")
        batch.drop_column("parent_review_artifact_id")
