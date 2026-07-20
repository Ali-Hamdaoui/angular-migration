"""Add execution lineage, idempotency identity, and evidence pointers."""

from alembic import op
import sqlalchemy as sa

revision = "20260720_11"
down_revision = "20260720_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        ("template_id", sa.String(64)), ("template_version", sa.Integer()),
        ("plan_id", sa.String(64)), ("plan_version", sa.Integer()),
        ("request_payload_hash", sa.String(128)), ("correlation_id", sa.String(128)),
        ("authoritative_state_version", sa.Integer()),
        ("safe_relative_working_directory", sa.String(512)), ("process_id", sa.Integer()),
        ("failure_code", sa.String(128)), ("failure_message", sa.Text()),
        ("manifest_artifact_id", sa.String(128)), ("result_artifact_id", sa.String(128)),
    )
    for name, column_type in columns:
        op.add_column("command_executions", sa.Column(name, column_type, nullable=True))
    op.create_index("ix_command_executions_request_payload_hash", "command_executions", ["request_payload_hash"])
    op.create_index("ix_command_executions_correlation_id", "command_executions", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_command_executions_correlation_id", table_name="command_executions")
    op.drop_index("ix_command_executions_request_payload_hash", table_name="command_executions")
    for name in ("result_artifact_id", "manifest_artifact_id", "failure_message", "failure_code", "process_id", "safe_relative_working_directory", "authoritative_state_version", "correlation_id", "request_payload_hash", "plan_version", "plan_id", "template_version", "template_id"):
        op.drop_column("command_executions", name)
