"""Bind stage workspace records to the sandbox request for safe replay."""

from alembic import op
import sqlalchemy as sa


revision = "20260721_01"
down_revision = "20260720_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stage_workspaces", sa.Column("request_idempotency_key", sa.String(128), nullable=True))
    op.add_column("stage_workspaces", sa.Column("request_binding_checksum", sa.String(128), nullable=True))
    op.add_column("stage_workspaces", sa.Column("locked_bindings", sa.JSON(), nullable=True))
    op.add_column("stage_workspaces", sa.Column("verification", sa.JSON(), nullable=True))
    op.add_column("g07_approvals", sa.Column("decision_idempotency_key", sa.String(128), nullable=True))
    op.add_column("g07_approvals", sa.Column("decision_request_checksum", sa.String(128), nullable=True))
    op.add_column("g07_approvals", sa.Column("prepare_request_checksum", sa.String(128), nullable=True))
    op.add_column("g07_approvals", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_g07_approvals_decision_idempotency", "g07_approvals", ["run_id", "decision_idempotency_key"], unique=True)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_g07_approvals_decision_idempotency")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, column in (
        ("g07_approvals", "prepare_request_checksum"),
        ("g07_approvals", "expires_at"),
        ("g07_approvals", "decision_request_checksum"),
        ("g07_approvals", "decision_idempotency_key"),
        ("stage_workspaces", "verification"),
        ("stage_workspaces", "locked_bindings"),
        ("stage_workspaces", "request_binding_checksum"),
        ("stage_workspaces", "request_idempotency_key"),
    ):
        if column in {item["name"] for item in inspector.get_columns(table)}:
            op.drop_column(table, column)
