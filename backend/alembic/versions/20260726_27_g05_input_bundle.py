"""Persist the immutable prerequisite bundle approved by G05."""

from alembic import op
import sqlalchemy as sa


revision = "20260726_27"
down_revision = "20260726_26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("g05_approvals") as batch:
        batch.add_column(sa.Column("prerequisite_artifact_ids", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("prerequisite_artifact_checksums", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("input_bundle_checksum", sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("g05_approvals") as batch:
        batch.drop_column("input_bundle_checksum")
        batch.drop_column("prerequisite_artifact_checksums")
        batch.drop_column("prerequisite_artifact_ids")
