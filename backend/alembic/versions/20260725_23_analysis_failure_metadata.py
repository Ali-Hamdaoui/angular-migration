"""Persist failed Analysis attempt metadata and safe subtype."""

from alembic import op
import sqlalchemy as sa

revision = "20260725_23"
down_revision = "20260725_22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_invocations") as batch:
        batch.add_column(sa.Column("failure_subtype", sa.String(128), nullable=True))
    with op.batch_alter_table("analysis_metadata") as batch:
        batch.add_column(sa.Column("failure_subtype", sa.String(128), nullable=True))
        batch.add_column(sa.Column("failure_stage", sa.String(128), nullable=True))
        batch.add_column(sa.Column("retryable", sa.Boolean(), nullable=True, server_default=sa.false()))
        batch.add_column(sa.Column("correlation_id", sa.String(128), nullable=True))
        batch.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analysis_metadata") as batch:
        for name in ("failed_at", "correlation_id", "retryable", "failure_stage", "failure_subtype"):
            batch.drop_column(name)
    with op.batch_alter_table("llm_invocations") as batch:
        batch.drop_column("failure_subtype")
