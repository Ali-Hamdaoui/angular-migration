"""Persist the immutable execution audit trail (V2 F27-03)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_67"
down_revision = "20260817_66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "command_execution_audits",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=True),
        sa.Column("execution_id", sa.String(length=64), nullable=True),
        sa.Column("command_id", sa.String(length=128), nullable=False),
        sa.Column("command_class", sa.String(length=64), nullable=False),
        sa.Column("event", sa.String(length=48), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("executable", sa.String(length=128), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=True),
        sa.Column("network_profile", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("prev_checksum", sa.String(length=128), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "execution_id", "occurred_at", "event", name="uq_cmd_exec_audit_run_exec_time_event"),
    )
    op.create_index("ix_command_execution_audits_run_id", "command_execution_audits", ["run_id"])
    op.create_index("ix_command_execution_audits_command_id", "command_execution_audits", ["command_id"])
    op.create_index("ix_command_execution_audits_event", "command_execution_audits", ["event"])
    op.create_index("ix_command_execution_audits_checksum", "command_execution_audits", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_command_execution_audits_checksum", table_name="command_execution_audits")
    op.drop_index("ix_command_execution_audits_event", table_name="command_execution_audits")
    op.drop_index("ix_command_execution_audits_command_id", table_name="command_execution_audits")
    op.drop_index("ix_command_execution_audits_run_id", table_name="command_execution_audits")
    op.drop_table("command_execution_audits")
