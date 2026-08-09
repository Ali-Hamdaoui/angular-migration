"""Separate execution-profile provenance and invalidate incomplete legacy G05 evidence."""

from alembic import op
import sqlalchemy as sa


revision = "20260727_29"
down_revision = "20260727_28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("compatibility_resolutions") as batch:
        batch.add_column(sa.Column("source_execution_profile_checksum", sa.String(128), nullable=True))
        batch.add_column(sa.Column("stage1_profile_checksum", sa.String(128), nullable=True))
    op.execute(
        """
        UPDATE g05_approvals
        SET status = 'stale',
            stale_reason = 'LEGACY_G05_INPUT_BUNDLE_MISSING',
            updated_at = CURRENT_TIMESTAMP
        WHERE status IN ('pending', 'approved')
          AND (
            prerequisite_artifact_ids IS NULL
            OR prerequisite_artifact_checksums IS NULL
            OR input_bundle_checksum IS NULL
            OR json_array_length(prerequisite_artifact_ids) = 0
            OR json_array_length(prerequisite_artifact_checksums) = 0
          )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("compatibility_resolutions") as batch:
        batch.drop_column("stage1_profile_checksum")
        batch.drop_column("source_execution_profile_checksum")
