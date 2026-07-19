"""Add failure_routes and failure_attempts tables for C-Lite routing."""

from alembic import op
import sqlalchemy as sa


revision = "20260719_08"
down_revision = "20260719_07"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "failure_routes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("failure_id", sa.String(64), nullable=False, index=True),
        sa.Column("route", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("decision_checksum", sa.String(128), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("risk", sa.String(32), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "failure_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("failure_id", sa.String(64), nullable=False, index=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("route", sa.String(64), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("failure_attempts")
    op.drop_table("failure_routes")
