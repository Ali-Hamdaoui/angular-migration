"""Align persisted preflight and source-snapshot metadata with ORM models."""

from alembic import op
import sqlalchemy as sa

revision = "20260716_03"
down_revision = "20260716_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_snapshots", sa.Column("execution_id", sa.String(length=64), nullable=True))
    op.add_column("source_snapshots", sa.Column("backend_instance_id", sa.String(length=128), nullable=True))
    op.add_column("source_snapshots", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_source_snapshots_execution_id", "source_snapshots", ["execution_id"])
    op.create_index("ix_source_snapshots_backend_instance_id", "source_snapshots", ["backend_instance_id"])
    op.create_index("ix_preflight_events_event_type", "preflight_events", ["event_type"])
    op.create_index("ix_preflight_events_idempotency_key", "preflight_events", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_preflight_events_idempotency_key", table_name="preflight_events")
    op.drop_index("ix_preflight_events_event_type", table_name="preflight_events")
    op.drop_index("ix_source_snapshots_backend_instance_id", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_execution_id", table_name="source_snapshots")
    op.drop_column("source_snapshots", "heartbeat_at")
    op.drop_column("source_snapshots", "backend_instance_id")
    op.drop_column("source_snapshots", "execution_id")