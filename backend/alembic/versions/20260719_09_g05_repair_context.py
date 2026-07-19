"""Create repair_context_packs table for RepairContextPack persistence.

Revision ID: 20260719_09_g05
Revises: 20260719_08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260719_09_g05"
down_revision = "20260719_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repair_context_packs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("failure_id", sa.String(64), nullable=False, index=True),
        sa.Column("stage_id", sa.String(64), nullable=False),
        sa.Column("repair_attempt", sa.Integer(), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("selection_policy_version", sa.String(32), nullable=False),
        sa.Column("sanitization_checksum", sa.String(128), nullable=False),
        sa.Column("content_checksum", sa.String(128), nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'finalized'")),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "failure_id", "repair_attempt", name="uq_repair_context_packs_failure_attempt"),
    )
    op.create_index("ix_repair_context_packs_run_id", "repair_context_packs", ["run_id"])
    op.create_index("ix_repair_context_packs_failure_id", "repair_context_packs", ["failure_id"])
    op.create_index("ix_repair_context_packs_status", "repair_context_packs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_repair_context_packs_status", table_name="repair_context_packs")
    op.drop_index("ix_repair_context_packs_failure_id", table_name="repair_context_packs")
    op.drop_index("ix_repair_context_packs_run_id", table_name="repair_context_packs")
    op.drop_table("repair_context_packs")
