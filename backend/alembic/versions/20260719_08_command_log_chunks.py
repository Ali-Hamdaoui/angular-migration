"""Add command_log_chunks table for G01 S3-F03 live log streaming."""

from alembic import op
import sqlalchemy as sa

revision = "20260719_08"
down_revision = "20260719_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "command_log_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("execution_id", sa.String(64), nullable=False, index=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stream", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("redacted", sa.Boolean(), nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("execution_id", "sequence", name="uq_cmd_log_chunks_exec_seq"),
    )
    op.create_index("ix_cmd_log_chunks_exec_seq", "command_log_chunks", ["execution_id", "sequence"])


def downgrade() -> None:
    op.drop_table("command_log_chunks")
