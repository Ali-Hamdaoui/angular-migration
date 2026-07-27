"""Persist recoverable post-G04 planning continuations."""

from alembic import op
import sqlalchemy as sa


revision = "20260726_26"
down_revision = "20260726_25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planning_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("current_step", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("worker_id", sa.String(128)),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("last_error_code", sa.String(128)),
        sa.Column("last_error_stage", sa.String(128)),
        sa.Column("retryable", sa.Boolean()),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_planning_jobs_run_idempotency"),
    )
    op.create_index("ix_planning_jobs_run_id", "planning_jobs", ["run_id"])
    op.create_index("ix_planning_jobs_status", "planning_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_planning_jobs_status", table_name="planning_jobs")
    op.drop_index("ix_planning_jobs_run_id", table_name="planning_jobs")
    op.drop_table("planning_jobs")
