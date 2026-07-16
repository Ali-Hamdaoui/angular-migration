"""Persist S1-F12 baseline validation matrix results."""

from alembic import op
import sqlalchemy as sa

revision = "20260716_04"
down_revision = "20260716_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "baseline_validations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("targets", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("parser_summary", sa.JSON()),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("prerequisite_artifact_ids", sa.JSON(), nullable=False),
        sa.Column("baseline_checksum", sa.String(length=128)),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_baseline_validations_run_idempotency"),
    )
    op.create_index("ix_baseline_validations_run_id", "baseline_validations", ["run_id"])
    op.create_index("ix_baseline_validations_kind", "baseline_validations", ["kind"])
    op.create_index("ix_baseline_validations_status", "baseline_validations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_baseline_validations_status", table_name="baseline_validations")
    op.drop_index("ix_baseline_validations_kind", table_name="baseline_validations")
    op.drop_index("ix_baseline_validations_run_id", table_name="baseline_validations")
    op.drop_table("baseline_validations")
