"""Persist per-chunk command-log metadata for API/SSE consumers."""

from alembic import op
import sqlalchemy as sa

revision = "20260720_14"
down_revision = "20260720_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("command_log_chunks", sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("command_log_chunks", sa.Column("byte_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("command_log_chunks", sa.Column("character_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("command_log_chunks", sa.Column("correlation_id", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("command_log_chunks", "correlation_id")
    op.drop_column("command_log_chunks", "character_count")
    op.drop_column("command_log_chunks", "byte_count")
    op.drop_column("command_log_chunks", "truncated")
