"""Add durable live command log summaries."""

from alembic import op
import sqlalchemy as sa

revision = "20260720_13"
down_revision = "20260720_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "command_log_summaries",
        sa.Column("execution_id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("first_sequence", sa.Integer()), sa.Column("last_sequence", sa.Integer()),
        sa.Column("stdout_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stderr_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stdout_stored_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stderr_stored_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stdout_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stderr_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("redaction_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("finalized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("correlation_id", sa.String(128)),
    )


def downgrade() -> None:
    op.drop_table("command_log_summaries")
