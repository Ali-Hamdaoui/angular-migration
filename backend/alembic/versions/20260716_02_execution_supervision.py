"""Persist baseline cancellation and worker supervision identity."""

from alembic import op
import sqlalchemy as sa

revision = "20260716_02"
down_revision = "20260716_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("command_executions", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("command_executions", sa.Column("cancel_requested_by", sa.String(length=128), nullable=True))
    op.add_column("command_executions", sa.Column("cancel_idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("worker_leases", sa.Column("execution_id", sa.String(length=64), nullable=True))
    op.add_column("worker_leases", sa.Column("backend_instance_id", sa.String(length=128), nullable=True))
    op.add_column("worker_leases", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_worker_leases_execution_id", "worker_leases", ["execution_id"])
    op.create_index("ix_worker_leases_backend_instance_id", "worker_leases", ["backend_instance_id"])


def downgrade() -> None:
    op.drop_index("ix_worker_leases_backend_instance_id", table_name="worker_leases")
    op.drop_index("ix_worker_leases_execution_id", table_name="worker_leases")
    for name in ("heartbeat_at", "backend_instance_id", "execution_id"):
        op.drop_column("worker_leases", name)
    for name in ("cancel_idempotency_key", "cancel_requested_by", "cancel_requested_at"):
        op.drop_column("command_executions", name)
