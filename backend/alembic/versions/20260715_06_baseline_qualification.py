"""Create durable S1-F10 baseline qualification records."""

from alembic import op
import sqlalchemy as sa

revision = "20260715_06"
down_revision = "20260715_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "baseline_qualifications",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("sandbox_path", sa.Text(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("sandbox_fingerprint", sa.String(length=128)),
        sa.Column("package", sa.JSON()), sa.Column("lockfile", sa.JSON()),
        sa.Column("sources", sa.JSON(), nullable=False), sa.Column("scripts", sa.JSON(), nullable=False),
        sa.Column("registry", sa.JSON()), sa.Column("blockers", sa.JSON(), nullable=False), sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("authorization_status", sa.String(length=32), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False), sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False), sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_baseline_qualifications_run_idempotency"),
    )
    op.create_index("ix_baseline_qualifications_run_id", "baseline_qualifications", ["run_id"])
    op.create_index("ix_baseline_qualifications_status", "baseline_qualifications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_baseline_qualifications_status", table_name="baseline_qualifications")
    op.drop_index("ix_baseline_qualifications_run_id", table_name="baseline_qualifications")
    op.drop_table("baseline_qualifications")
