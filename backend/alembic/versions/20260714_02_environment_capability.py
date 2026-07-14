"""Persist environment capability snapshots and diagnostic events."""

from alembic import op
import sqlalchemy as sa

revision = "20260714_02"
down_revision = "20260710_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environment_capability_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_environment_capability_idempotency"),
    )
    op.create_index(
        "ix_environment_capability_snapshots_status",
        "environment_capability_snapshots",
        ["status"],
    )
    op.create_table(
        "environment_diagnostic_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_environment_diagnostic_events_snapshot_id",
        "environment_diagnostic_events",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_environment_diagnostic_events_event_type",
        "environment_diagnostic_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_environment_diagnostic_events_event_type", table_name="environment_diagnostic_events")
    op.drop_index("ix_environment_diagnostic_events_snapshot_id", table_name="environment_diagnostic_events")
    op.drop_table("environment_diagnostic_events")
    op.drop_index("ix_environment_capability_snapshots_status", table_name="environment_capability_snapshots")
    op.drop_table("environment_capability_snapshots")