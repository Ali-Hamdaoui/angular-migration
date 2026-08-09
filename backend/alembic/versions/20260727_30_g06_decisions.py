"""Persist immutable G06 decision replay evidence separately from the gate."""

from alembic import op
import sqlalchemy as sa


revision = "20260727_30"
down_revision = "20260727_29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("g05_approvals") as batch:
        batch.add_column(sa.Column("request_checksum", sa.String(128), nullable=True))
    op.create_table(
        "g06_decisions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("plan_checksum", sa.String(128), nullable=False),
        sa.Column("stage_plan_checksum", sa.String(128), nullable=False),
        sa.Column("expected_state_version", sa.Integer(), nullable=False),
        sa.Column("resulting_state_version", sa.Integer(), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128)),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g06_decisions_run_idempotency"),
    )
    op.create_index("ix_g06_decisions_run_id", "g06_decisions", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_g06_decisions_run_id", table_name="g06_decisions")
    op.drop_table("g06_decisions")
    with op.batch_alter_table("g05_approvals") as batch:
        batch.drop_column("request_checksum")
