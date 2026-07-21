"""Persist source-intake work before dispatching a worker."""

from alembic import op
import sqlalchemy as sa


revision = "20260721_16"
down_revision = "20260720_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_intake_jobs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_source_intake_jobs_run"),
    )
    op.create_index("ix_source_intake_jobs_run_id", "source_intake_jobs", ["run_id"])
    op.create_index("ix_source_intake_jobs_status", "source_intake_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_source_intake_jobs_status", table_name="source_intake_jobs")
    op.drop_index("ix_source_intake_jobs_run_id", table_name="source_intake_jobs")
    op.drop_table("source_intake_jobs")
