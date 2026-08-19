"""Persist evidence for an authorized interrupted-preparation drift."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_76"
down_revision = "20260819_75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stage_recovery_operations",
        sa.Column("observed_workspace_fingerprint", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "stage_recovery_operations",
        sa.Column("governed_workspace_fingerprint", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "stage_recovery_operations",
        sa.Column("drift_classification", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "stage_recovery_operations",
        sa.Column("interrupted_evidence_checksum", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stage_recovery_operations", "interrupted_evidence_checksum")
    op.drop_column("stage_recovery_operations", "drift_classification")
    op.drop_column("stage_recovery_operations", "governed_workspace_fingerprint")
    op.drop_column("stage_recovery_operations", "observed_workspace_fingerprint")
