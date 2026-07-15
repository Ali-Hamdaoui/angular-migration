"""Persist G02 review packages and immutable source-integrity decisions."""
from alembic import op
import sqlalchemy as sa

revision = "20260715_04"
down_revision = "20260715_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "g02_approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(64)),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("baseline_input_boundary", sa.String(64)),
        sa.Column("package", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("stale_reason", sa.Text()),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g02_approvals_run_idempotency"),
    )
    op.create_index("ix_g02_approvals_run_id", "g02_approvals", ["run_id"])
    op.create_index("ix_g02_approvals_status", "g02_approvals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_g02_approvals_status", table_name="g02_approvals")
    op.drop_index("ix_g02_approvals_run_id", table_name="g02_approvals")
    op.drop_table("g02_approvals")
