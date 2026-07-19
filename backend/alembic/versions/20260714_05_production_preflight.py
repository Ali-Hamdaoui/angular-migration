"""Persist checksum-bound production preflights and G01 decisions."""

from alembic import op
import sqlalchemy as sa

revision = "20260714_05"
down_revision = "20260714_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("preflights", sa.Column("id", sa.String(64), primary_key=True), sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("actor", sa.String(128), nullable=False), sa.Column("gate_id", sa.String(64), nullable=False), sa.Column("gate_version", sa.String(64), nullable=False), sa.Column("state_version", sa.Integer, nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("input_checksum", sa.String(128), nullable=False), sa.Column("artifact_set_checksum", sa.String(128), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("binding", sa.JSON, nullable=False), sa.Column("snapshot", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("idempotency_key", name="uq_preflights_idempotency"))
    op.create_index("ix_preflights_status", "preflights", ["status"])
    op.create_table("approval_gates", sa.Column("id", sa.String(64), primary_key=True), sa.Column("preflight_id", sa.String(64), nullable=False), sa.Column("gate_id", sa.String(64), nullable=False), sa.Column("gate_version", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("state_version", sa.Integer, nullable=False), sa.Column("input_checksum", sa.String(128), nullable=False), sa.Column("artifact_set_checksum", sa.String(128), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("preflight_id", "gate_id", name="uq_approval_gates_preflight_gate"))
    op.create_index("ix_approval_gates_preflight_id", "approval_gates", ["preflight_id"])
    op.create_index("ix_approval_gates_status", "approval_gates", ["status"])
    op.create_table("user_decisions", sa.Column("id", sa.String(64), primary_key=True), sa.Column("preflight_id", sa.String(64), nullable=False), sa.Column("gate_id", sa.String(64), nullable=False), sa.Column("decision", sa.String(64), nullable=False), sa.Column("actor", sa.String(128), nullable=False), sa.Column("comment", sa.Text), sa.Column("input_checksum", sa.String(128), nullable=False), sa.Column("artifact_set_checksum", sa.String(128), nullable=False), sa.Column("state_version", sa.Integer, nullable=False), sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("idempotency_key", name="uq_user_decisions_idempotency"))
    op.create_index("ix_user_decisions_preflight_id", "user_decisions", ["preflight_id"])
    op.create_index("ix_user_decisions_gate_id", "user_decisions", ["gate_id"])
    op.create_table("preflight_events", sa.Column("id", sa.String(64), primary_key=True), sa.Column("preflight_id", sa.String(64), nullable=False), sa.Column("event_type", sa.String(128), nullable=False), sa.Column("actor", sa.String(128)), sa.Column("idempotency_key", sa.String(128)), sa.Column("payload", sa.JSON, nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("sequence", sa.Integer, nullable=False, server_default="0"))
    op.create_index("ix_preflight_events_preflight_id", "preflight_events", ["preflight_id"])
    op.create_table("preflight_artifact_metadata", sa.Column("id", sa.String(64), primary_key=True), sa.Column("preflight_id", sa.String(64), nullable=False), sa.Column("artifact_id", sa.String(64), nullable=False), sa.Column("artifact_type", sa.String(64), nullable=False), sa.Column("relative_path", sa.Text, nullable=False), sa.Column("checksum", sa.String(128), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("artifact_id", name="uq_preflight_artifact_metadata_artifact_id"))
    op.create_index("ix_preflight_artifact_metadata_preflight_id", "preflight_artifact_metadata", ["preflight_id"])


def downgrade() -> None:
    op.drop_index("ix_preflight_artifact_metadata_preflight_id", table_name="preflight_artifact_metadata")
    op.drop_table("preflight_artifact_metadata")
    op.drop_table("preflight_events")
    op.drop_table("user_decisions")
    op.drop_table("approval_gates")
    op.drop_table("preflights")
