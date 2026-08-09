"""Add durable planning retry timing and failure provenance."""

from alembic import op
import sqlalchemy as sa

revision = "20260727_28"
down_revision = "20260726_27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("planning_jobs") as batch:
        batch.add_column(sa.Column("max_attempts", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_error_message", sa.Text(), nullable=True))
        batch.add_column(sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("terminal_failed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE planning_jobs SET max_attempts = 3 WHERE max_attempts IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("planning_jobs") as batch:
        batch.drop_column("terminal_failed_at")
        batch.drop_column("first_failed_at")
        batch.drop_column("last_error_message")
        batch.drop_column("next_attempt_at")
        batch.drop_column("max_attempts")
