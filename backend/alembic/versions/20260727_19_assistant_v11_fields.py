"""Additive V1.1 Assistant request, retry, version and response metadata."""

from alembic import op
import sqlalchemy as sa

revision = "20260727_19"
down_revision = "20260723_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, column in (
        ("request_id", sa.Column("request_id", sa.String(128))),
        ("retry_of_message_id", sa.Column("retry_of_message_id", sa.String(64))),
        ("semantic_state_version", sa.Column("semantic_state_version", sa.Integer(), nullable=False, server_default="1")),
        ("operational_event_sequence", sa.Column("operational_event_sequence", sa.Integer(), nullable=False, server_default="0")),
        ("intent", sa.Column("intent", sa.String(64), nullable=False, server_default="unsupported")),
        ("capability_key", sa.Column("capability_key", sa.String(128), nullable=False, server_default="")),
        ("answer_mode", sa.Column("answer_mode", sa.String(32), nullable=False, server_default="concise")),
    ):
        op.add_column("assistant_messages", column)
    op.create_index("ix_assistant_messages_request_id", "assistant_messages", ["request_id"])
    op.create_index("ix_assistant_messages_retry_of_message_id", "assistant_messages", ["retry_of_message_id"])


def downgrade() -> None:
    op.drop_index("ix_assistant_messages_retry_of_message_id", table_name="assistant_messages")
    op.drop_index("ix_assistant_messages_request_id", table_name="assistant_messages")
    for name in ("answer_mode", "capability_key", "intent", "operational_event_sequence", "semantic_state_version", "retry_of_message_id", "request_id"):
        op.drop_column("assistant_messages", name)
