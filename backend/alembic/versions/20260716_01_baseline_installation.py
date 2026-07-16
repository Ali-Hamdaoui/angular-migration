"""Persist S1-F11 baseline installation execution evidence."""

from alembic import op
import sqlalchemy as sa

revision = "20260716_01"
down_revision = "20260715_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        ("command_id", sa.String(length=128), False),
        ("requester", sa.String(length=128), True),
        ("shell", sa.Boolean(), False),
        ("timeout_seconds", sa.Integer(), False),
        ("network_profile", sa.String(length=128), False),
        ("cancellation_policy", sa.String(length=64), False),
        ("runtime_checksum", sa.String(length=128), True),
        ("baseline_checksum", sa.String(length=128), True),
        ("duration_ms", sa.Integer(), True),
        ("timed_out", sa.Boolean(), False),
        ("cancelled", sa.Boolean(), False),
        ("reconstruction_required", sa.Boolean(), False),
        ("worker_id", sa.String(length=128), True),
        ("stdout_artifact_id", sa.String(length=128), True),
        ("stderr_artifact_id", sa.String(length=128), True),
        ("command_log_artifact_id", sa.String(length=128), True),
        ("artifact_ids", sa.JSON(), False),
        ("start_fingerprint", sa.JSON(), True),
        ("end_fingerprint", sa.JSON(), True),
        ("blockers", sa.JSON(), False),
        ("environment_blocker", sa.String(length=128), True),
        ("state_version", sa.Integer(), False),
        ("event_sequence", sa.Integer(), False),
    )
    for name, column_type, nullable in columns:
        op.add_column("command_executions", sa.Column(name, column_type, nullable=True))
    op.create_index("ix_command_executions_command_id", "command_executions", ["command_id"])


def downgrade() -> None:
    op.drop_index("ix_command_executions_command_id", table_name="command_executions")
    for name in (
        "event_sequence", "state_version", "environment_blocker", "blockers",
        "end_fingerprint", "start_fingerprint", "artifact_ids",
        "command_log_artifact_id", "stderr_artifact_id", "stdout_artifact_id",
        "worker_id", "reconstruction_required", "cancelled", "timed_out",
        "duration_ms", "baseline_checksum", "runtime_checksum",
        "cancellation_policy", "network_profile", "timeout_seconds", "shell",
        "requester", "command_id",
    ):
        op.drop_column("command_executions", name)