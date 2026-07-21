"""Align persisted schema with the current workflow ORM contract."""

from alembic import op
import sqlalchemy as sa


revision = "20260720_15"
down_revision = "20260720_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Migration 12 introduced these fields as nullable for legacy rows. The
    # current artifact contract requires explicit boolean values.
    op.execute(sa.text("UPDATE artifact_metadata SET immutable = COALESCE(immutable, 1), redacted = COALESCE(redacted, 0), truncated = COALESCE(truncated, 0)"))
    with op.batch_alter_table("artifact_metadata") as batch_op:
        batch_op.alter_column("immutable", existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column("redacted", existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column("truncated", existing_type=sa.Boolean(), nullable=False)

    op.drop_index("ix_active_plan_versions_run_id", table_name="active_plan_versions")
    op.create_index("ix_command_executions_authoritative_state_version", "command_executions", ["authoritative_state_version"])


def downgrade() -> None:
    op.drop_index("ix_command_executions_authoritative_state_version", table_name="command_executions")
    op.create_index("ix_active_plan_versions_run_id", "active_plan_versions", ["run_id"])
    with op.batch_alter_table("artifact_metadata") as batch_op:
        batch_op.alter_column("immutable", existing_type=sa.Boolean(), nullable=True)
        batch_op.alter_column("redacted", existing_type=sa.Boolean(), nullable=True)
        batch_op.alter_column("truncated", existing_type=sa.Boolean(), nullable=True)
