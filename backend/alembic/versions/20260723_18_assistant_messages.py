"""Persist run-scoped assistant conversations."""

from alembic import op
import sqlalchemy as sa

revision = "20260723_18"
down_revision = "20260721_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "conversation_id", name="uq_assistant_conversation_run"),
    )
    op.create_index("ix_assistant_conversations_run_id", "assistant_conversations", ["run_id"])
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("message_id", sa.String(64), nullable=False, unique=True),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("message_order", sa.Integer, nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("input_manifest", sa.JSON, nullable=False),
        sa.Column("input_manifest_checksum", sa.String(128), nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False),
        sa.Column("projection", sa.JSON, nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("proof_label", sa.String(64), nullable=False),
        sa.Column("usage", sa.JSON, nullable=False),
        sa.Column("model_provenance", sa.JSON, nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_assistant_message_run_idempotency"),
    )
    op.create_index("ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"])
    op.create_index("ix_assistant_messages_run_id", "assistant_messages", ["run_id"])
    op.create_index("ix_assistant_messages_conversation_order", "assistant_messages", ["conversation_id", "message_order"])
    op.create_table(
        "assistant_lifecycle_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sequence", name="uq_assistant_lifecycle_run_sequence"),
        sa.UniqueConstraint("run_id", "idempotency_key", "event_type", name="uq_assistant_lifecycle_request_event"),
    )
    op.create_index("ix_assistant_lifecycle_events_run_id", "assistant_lifecycle_events", ["run_id"])
    op.create_index("ix_assistant_lifecycle_events_conversation_id", "assistant_lifecycle_events", ["conversation_id"])
    op.create_index("ix_assistant_lifecycle_events_event_type", "assistant_lifecycle_events", ["event_type"])
    op.create_index("ix_assistant_lifecycle_run_sequence", "assistant_lifecycle_events", ["run_id", "sequence"])


def downgrade() -> None:
    op.drop_table("assistant_lifecycle_events")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
