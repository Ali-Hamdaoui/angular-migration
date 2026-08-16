"""Persist lockfile generation evidence (V2 F08-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_51"
down_revision = "20260816_50"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lockfile_generation_evidence",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("execution_id", sa.String(length=64), nullable=True),
        sa.Column("lockfile_checksum", sa.String(length=128), nullable=False),
        sa.Column("lockfile_version", sa.Integer(), nullable=True),
        sa.Column("source_family", sa.String(length=32), nullable=False),
        sa.Column("target_family", sa.String(length=32), nullable=False),
        sa.Column("node_version", sa.String(length=64), nullable=True),
        sa.Column("npm_version", sa.String(length=64), nullable=True),
        sa.Column("node_sha256", sa.String(length=64), nullable=True),
        sa.Column("npm_sha256", sa.String(length=64), nullable=True),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lockfile_evidence_run_stage", "lockfile_generation_evidence", ["run_id", "stage_id"])


def downgrade() -> None:
    op.drop_index("ix_lockfile_evidence_run_stage", table_name="lockfile_generation_evidence")
    op.drop_table("lockfile_generation_evidence")
